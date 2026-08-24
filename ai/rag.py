"""RAG orchestration for the AI Librarian (AGENTS.md sections 8/9/12/29).

Pipeline: question -> permission-filtered retrieval (search services) ->
numbered source blocks -> grounded generation -> citation validation.

Hard rules enforced here:
- Retrieved document text is DATA, never instructions; the system prompt
  says so explicitly and context is wrapped in unambiguous delimiters.
- Grounded scopes answer only from provided sources; when retrieval finds
  nothing, we answer honestly WITHOUT calling the model (no hallucination
  surface, no wasted tokens).
- Citations [n] may only reference blocks that were actually provided;
  invalid markers are stripped and flagged.
- Prompts are versioned (RAG_PROMPT_VERSION) and recorded per interaction.
"""

import re

from django.conf import settings

from ai.models import AIInteraction
from ai.prompts import (
    DATA_CLOSE,
    DATA_OPEN,
    INSUFFICIENT_MESSAGE,
)
from ai.prompts import (
    LIBRARIAN_SYSTEM_PROMPT as SYSTEM_PROMPT,
)
from ai.providers import AIError, get_chat_provider
from ai.ratelimit import enforce as check_rate_limit
from search.services import hybrid_search

_CITATION_PATTERN = re.compile(r"\[(\d{1,2})\]")


def _block_text(number, result):
    chunk = result.chunk
    resource = chunk.resource
    location = []
    if chunk.chapter:
        location.append(f"chapter: {chunk.chapter.title}")
    if chunk.section:
        location.append(f"section: {chunk.section.title}")
    pages = "page"
    if chunk.page_start and chunk.page_end and chunk.page_start != chunk.page_end:
        pages = f"pages {chunk.page_start}-{chunk.page_end}"
    elif chunk.page_start:
        pages = f"page {chunk.page_start}"
    header = f"[{number}] {resource.title}"
    if location or pages:
        header += " (" + "; ".join([*location, pages]) + ")"
    return f"{header}\n{chunk.text.strip()}"


def build_context(results, max_chars=None):
    """Format retrieved chunks as numbered, delimited source blocks."""
    max_chars = max_chars or getattr(settings, "RAG_MAX_CONTEXT_CHARS", 6000)
    blocks, used = [], 0
    for number, result in enumerate(results, start=1):
        block = _block_text(number, result)
        if used + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join([DATA_OPEN, *blocks, DATA_CLOSE]), len(blocks)


def extract_citations(answer_text, block_count):
    """Return sorted valid citation numbers found in the answer."""
    valid = set()
    for match in _CITATION_PATTERN.findall(answer_text):
        number = int(match)
        if 1 <= number <= block_count:
            valid.add(number)
    return sorted(valid)


def sanitize_citations(answer_text, block_count):
    """Strip citation markers that reference non-existent blocks."""
    def replace(match):
        number = int(match.group(1))
        return match.group(0) if 1 <= number <= block_count else ""

    cleaned = _CITATION_PATTERN.sub(replace, answer_text)
    return cleaned, extract_citations(cleaned, block_count)


def resolve_scope(user, scope, resource_public_id=None, chapter_id=None):
    """Translate a requested scope into search-scope kwargs + label.

    Raises Resource.DoesNotExist/Http404-able ValueError when the target
    material is not visible to the user.
    """
    from library.services import visible_resources

    scope = (scope or AIInteraction.Scope.LIBRARY).upper()
    search_scope = {}
    if scope == AIInteraction.Scope.BOOK:
        resource = visible_resources(user).filter(public_id=resource_public_id).first()
        if resource is None:
            raise ValueError("Book not found in your library.")
        search_scope = {"resource": str(resource.public_id)}
    elif scope == AIInteraction.Scope.CHAPTER:
        from library.models import BookChapter

        chapter = BookChapter.objects.filter(pk=chapter_id).select_related("resource").first()
        if chapter is None or not visible_resources(user).filter(
            pk=chapter.resource_id
        ).exists():
            raise ValueError("Chapter not found in your library.")
        search_scope = {"resource": str(chapter.resource.public_id)}
    elif scope == AIInteraction.Scope.SUBJECT:
        search_scope = {"subject": resource_public_id}
    elif scope == AIInteraction.Scope.CLASS:
        search_scope = {"school_class": resource_public_id}
    return scope, search_scope


class QuestionTooLong(ValueError):
    """Raised when a question exceeds MAX_QUESTION_LENGTH."""


MAX_QUESTION_LENGTH = 5000


def validate_question(question):
    """Validate a question for the AI Librarian. Raises ValueError."""
    if len(question) > MAX_QUESTION_LENGTH:
        raise QuestionTooLong(
            f"Questions are limited to {MAX_QUESTION_LENGTH} characters "
            f"(you sent {len(question)})."
        )


def ask(user, question, scope=AIInteraction.Scope.LIBRARY,
        resource_public_id=None, chapter_id=None, chat_provider=None):
    """Answer a question with library-grounded RAG. Returns AIInteraction."""

    validate_question(question)
    check_rate_limit(user)

    scope_label, search_scope = resolve_scope(
        user, scope, resource_public_id, chapter_id
    )
    grounded = scope_label != AIInteraction.Scope.GENERAL
    normalized = normalize_question(question)

    cache_key = None
    if grounded and getattr(settings, "RAG_USE_CACHE", True):
        cache_key = _answer_cache_key(
            user, scope_label, normalized, chat_provider,
            getattr(settings, "RAG_PROMPT_VERSION", "rag-v1"),
        )
        if cache_key is not None:
            from django.core.cache import cache

            hit = cache.get(cache_key)
            if hit is not None:
                interaction = AIInteraction(
                    user=user,
                    school=user.school,
                    scope=scope_label,
                    question=question.strip(),
                    prompt_version=getattr(settings, "RAG_PROMPT_VERSION", "rag-v1"),
                    retrieved_count=len(hit.get("chunk_ids", [])),
                    answer=hit["answer"],
                    cited_chunk_ids=hit.get("chunk_ids", []),
                    used_provider=False,
                )
                interaction.save()
                return interaction

    results = []
    if grounded:
        results = hybrid_search(user, question, search_scope, limit=getattr(settings, "RAG_TOP_K", 8))

    interaction = AIInteraction(
        user=user,
        school=user.school,
        scope=scope_label,
        question=question.strip(),
        prompt_version=getattr(settings, "RAG_PROMPT_VERSION", "rag-v1"),
        retrieved_count=len(results),
    )

    if grounded and not results:
        interaction.answer = INSUFFICIENT_MESSAGE
        interaction.used_provider = False
        interaction.cited_chunk_ids = []
        interaction.save()
        return interaction

    context, block_count = build_context(results)
    provider = chat_provider or get_chat_provider()
    user_prompt = (
        f"Question: {question}\n\n"
        f"Answer using only the numbered sources above where relevant. "
        f"Cite blocks like [1]."
        if grounded
        else question
    )
    if grounded:
        full_prompt = f"{context}\n\n{user_prompt}"
    else:
        full_prompt = user_prompt

    try:
        from ai.budget import enforce_budget
        from ai.context import school_context

        enforce_budget(user.school)
        with school_context(user.school):
            result = provider.generate(full_prompt, system=SYSTEM_PROMPT)
    except AIError as exc:
        interaction.answer = (
            "The AI service is temporarily unavailable. Please try again shortly."
        )
        interaction.used_provider = False
        interaction.save()
        raise AIError(str(exc)) from exc

    answer_text, cited_numbers = sanitize_citations(result.text, block_count)
    cited_chunk_ids = []
    for number in cited_numbers:
        cited_chunk_ids.append(results[number - 1].chunk.pk)

    interaction.answer = answer_text.strip()
    interaction.model = result.model
    interaction.used_provider = True
    interaction.cited_chunk_ids = cited_chunk_ids
    interaction.save()
    if cache_key is not None:
        from django.core.cache import cache

        cache.set(
            cache_key,
            {"answer": interaction.answer, "chunk_ids": cited_chunk_ids},
            getattr(settings, "RAG_CACHE_TTL", 86400),
        )
    return interaction


def normalize_question(question):
    """Cache-normalized form of a question (lower, whitespace-collapsed)."""
    return " ".join((question or "").strip().lower().split())


def _answer_cache_key(user, scope_label, normalized, chat_provider, prompt_version):
    """A deterministic cache key, or None when the chat model is unknown.

    Model-unknown (e.g. chat provider not configured) means the answer must
    not be cached under a generic key that could collide across models.
    """
    import hashlib

    from django.core.cache import cache

    from library.models import Resource

    if chat_provider is not None:
        model = getattr(chat_provider, "model", "")
    else:
        try:
            model = get_chat_provider().model
        except AIError:
            return None
    if not model:
        return None

    version_key = f"school-res-ver:{user.school_id}"
    version = cache.get(version_key)
    if version is None:
        latest = (
            Resource.objects.filter(school_id=user.school_id)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        version = latest.timestamp() if latest else 0
        cache.set(version_key, version, 60)
    fingerprint = hashlib.sha256(normalized.encode()).hexdigest()
    scope = (user.school_id or 0)
    return f"rag:{scope}:{scope_label}:{version}:{model}:{prompt_version}:{fingerprint}"


def sources_for(interaction):
    """Source-inspection data for an answer: the chunks it cited."""
    from documents.models import DocumentChunk

    chunk_ids = interaction.cited_chunk_ids or []
    if not chunk_ids:
        return []
    chunks = DocumentChunk.objects.select_related(
        "resource", "chapter", "section"
    ).filter(pk__in=chunk_ids)
    by_id = {chunk.pk: chunk for chunk in chunks}
    return [by_id[cid] for cid in chunk_ids if cid in by_id]
