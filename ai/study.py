"""AI study tools: summaries, revision notes, definitions/formulae,
practice questions - always generated FROM retrieved school material
(never from thin air), with the same citation discipline as the AI
Librarian (AGENTS.md sections 12/14, SKILLS.md sections 8/9).

Outputs are study SUPPORT: clearly AI-generated, never teacher-approved,
and never written into the question bank (that is Phase 7 with approval).
"""

from django.conf import settings

from ai.models import AIGeneration, AIInteraction
from ai.prompts import (
    LIBRARIAN_SYSTEM_PROMPT,
    STUDY_ADDENDUM,
)
from ai.providers import AIError, get_chat_provider
from ai.rag import build_context, resolve_scope, sanitize_citations, sources_for
from ai.ratelimit import enforce as check_rate_limit
from library.models import Resource
from search.services import hybrid_search

STUDY_SYSTEM_PROMPT = LIBRARIAN_SYSTEM_PROMPT + STUDY_ADDENDUM

STUDY_TASKS = {
    AIGeneration.Kind.SUMMARY: (
        "Produce a concise summary of the material above. Cover the main "
        "ideas in the order they appear, with a [n] citation per point."
    ),
    AIGeneration.Kind.REVISION_NOTES: (
        "Produce revision notes for the material above: short headings, "
        "bullet points, key terms in bold-style capital letters, and a [n] "
        "citation on every factual bullet."
    ),
    AIGeneration.Kind.DEFINITIONS_FORMULAE: (
        "Extract the key definitions and formulae from the material above. "
        "Format each as 'TERM - definition' or 'FORMULA - meaning', one per "
        "line, each with its [n] citation. Include only what appears in the "
        "documents."
    ),
    AIGeneration.Kind.PRACTICE_QUESTIONS: (
        "Generate practice questions from the material above. Format each "
        "as:\nQ: <question> [n]\nA: <model answer>\nUse exactly this Q:/A: "
        "format, one blank line between items. Every question must be "
        "answerable from the documents alone."
    ),
}

_KIND_RETRIEVAL_QUERIES = {
    AIGeneration.Kind.SUMMARY: "main ideas overview",
    AIGeneration.Kind.REVISION_NOTES: "key facts revision",
    AIGeneration.Kind.DEFINITIONS_FORMULAE: "definitions formulae terminology",
    AIGeneration.Kind.PRACTICE_QUESTIONS: "important concepts examples",
}


def _scope_target_resource(user, scope, resource_public_id=None, chapter_id=None):
    """Return the Resource targeted by BOOK/CHAPTER scopes, else None."""
    if scope == AIInteraction.Scope.BOOK:
        return (
            Resource.objects.filter(public_id=resource_public_id).first()
            if resource_public_id
            else None
        )
    if scope == AIInteraction.Scope.CHAPTER and chapter_id:
        from library.models import BookChapter

        chapter = BookChapter.objects.filter(pk=chapter_id).select_related("resource").first()
        return chapter.resource if chapter else None
    return None


def _insufficient(kind):
    return AIGeneration(
        kind=kind,
        content=(
            f"No relevant material was found for this {AIGeneration.Kind(kind).label.lower()} "
            "in the selected scope. Widen the scope or choose material that has "
            "finished processing."
        ),
        used_provider=False,
    )


def _broad_scope_results(user, search_scope):
    """Whole-scope chunk selection when no focus topic narrows retrieval."""
    from search.services import _candidate_chunks

    limit = getattr(settings, "RAG_TOP_K", 8)
    return list(_candidate_chunks(user, search_scope)[:limit])


class _ResultAdapter:
    """Wraps a chunk so rag.build_context can format it uniformly."""

    def __init__(self, chunk):
        self.chunk = chunk


def generate_study_material(user, kind, scope=AIInteraction.Scope.LIBRARY,
                            resource_public_id=None, chapter_id=None,
                            topic="", chat_provider=None):
    """Create one AIGeneration of the requested kind. Returns the saved row."""
    if kind not in AIGeneration.Kind.values:
        raise ValueError(f"Unknown study material kind: {kind}")

    check_rate_limit(user)
    scope_label, search_scope = resolve_scope(
        user, scope, resource_public_id, chapter_id
    )

    if topic.strip():
        query_parts = [_KIND_RETRIEVAL_QUERIES[kind], topic.strip()]
        results = hybrid_search(
            user, " ".join(query_parts), search_scope,
            limit=getattr(settings, "RAG_TOP_K", 8),
        )
    else:
        # No focus topic: use the scope's own chunks in document order -
        # e.g. 'summarize this book' means the book, not a similarity race.
        results = [
            _ResultAdapter(chunk)
            for chunk in _broad_scope_results(user, search_scope)
        ]

    generation = AIGeneration(
        user=user,
        school=user.school,
        kind=kind,
        scope=scope_label,
        source_resource=_scope_target_resource(user, scope_label, resource_public_id, chapter_id),
        topic=topic.strip()[:300],
        prompt_version=getattr(settings, "STUDY_PROMPT_VERSION", "study-v1"),
        retrieved_count=len(results),
    )

    if not results:
        fallback = _insufficient(kind)
        generation.content = fallback.content
        generation.used_provider = False
        generation.save()
        return generation

    context, block_count = build_context(results)
    task = STUDY_TASKS[kind]
    if topic.strip():
        task += f"\nFocus topic: {topic.strip()}"
    provider = chat_provider or get_chat_provider()

    try:
        from ai.budget import enforce_budget
        from ai.context import school_context

        enforce_budget(user.school)
        with school_context(user.school):
            result = provider.generate(
                f"{context}\n\n{task}", system=STUDY_SYSTEM_PROMPT
            )
    except AIError as exc:
        generation.content = (
            "The AI service is temporarily unavailable. Please try again shortly."
        )
        generation.used_provider = False
        generation.save()
        raise AIError(str(exc)) from exc

    content, cited_numbers = sanitize_citations(result.text, block_count)
    generation.content = content.strip()
    generation.model = result.model
    generation.used_provider = True
    generation.cited_chunk_ids = [
        results[number - 1].chunk.pk for number in cited_numbers
    ]
    generation.save()
    return generation


def sources_for(generation):  # re-exported alias for view symmetry with rag
    from ai.rag import sources_for as rag_sources_for

    return rag_sources_for(generation)