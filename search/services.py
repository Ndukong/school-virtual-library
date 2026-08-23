"""Search services: keyword, semantic, and hybrid retrieval.

Permission filtering always happens BEFORE content is retrieved or exposed
(AGENTS.md section 4 / SKILLS.md section 4): every query starts from the set
of chunks belonging to resources the user may read, then ranks within it.
Semantic ranking runs in Python over stored vectors today; swapping to
pgvector later changes storage, not this interface.
"""

import math
import re
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q

from ai.providers import get_provider, AIError
from documents.models import ChunkEmbedding, DocumentChunk
from library.models import Resource
from library.services import visible_resources


@dataclass
class SearchResult:
    chunk: DocumentChunk
    keyword_rank: int = None  # noqa: RUF012 - dataclass default None fine
    semantic_score: float = None
    fused_score: float = 0.0

    @property
    def resource(self):
        return self.chunk.resource


def _candidate_chunks(user, scope):
    """Chunks under permission + scope filters. Scope keys are validated here."""
    queryset = DocumentChunk.objects.select_related(
        "resource", "chapter", "section", "resource__subject"
    ).filter(resource__in=visible_resources(user))
    allowed_scopes = {
        "resource": lambda qs, value: qs.filter(resource__public_id=value),
        "subject": lambda qs, value: qs.filter(resource__subject_id=value),
        "school_class": lambda qs, value: qs.filter(resource__school_class_id=value),
        "resource_type": lambda qs, value: (
            qs.filter(resource__resource_type=value)
            if value in Resource.ResourceType.values
            else qs
        ),
    }
    for key, value in (scope or {}).items():
        apply_scope = allowed_scopes.get(key)
        if apply_scope and value:
            queryset = apply_scope(queryset, value)
    return queryset.order_by("resource_id", "sequence")


def _terms(query):
    """Tokenize a query into searchable terms (punctuation stripped)."""
    return re.findall(r"[A-Za-z0-9]{2,}", query or "")[:12]


def keyword_search(user, query, scope=None, limit=None):
    """Rank chunks by simple term coverage against the visible candidate set."""
    limit = limit or getattr(settings, "SEARCH_KEYWORD_TOP_K", 12)
    terms = _terms(query)
    if not terms:
        return []
    candidates = _candidate_chunks(user, scope).filter(
        reduce_or([Q(text__icontains=t) for t in terms])
    )[:500]
    scored = []
    lowered_query = query.strip().lower()
    for chunk in candidates:
        text = chunk.text.lower()
        matched = sum(1 for t in terms if t.lower() in text)
        score = matched + (3 if lowered_query in text else 0)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1].resource_id, pair[1].sequence))
    return [
        SearchResult(chunk=chunk, keyword_rank=index + 1)
        for index, (_, chunk) in enumerate(scored[:limit])
    ]


def reduce_or(q_objects):
    combined = q_objects[0]
    for q_object in q_objects[1:]:
        combined |= q_object
    return combined


def cosine_similarity(a, b):
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_search(user, query, scope=None, limit=None):
    """Embed the query and rank stored chunk vectors within visible scope."""
    limit = limit or getattr(settings, "SEARCH_SEMANTIC_TOP_K", 12)
    min_similarity = getattr(settings, "SEARCH_MIN_SIMILARITY", 0.15)
    if not query.strip():
        return []
    embeddings = ChunkEmbedding.objects.select_related(
        "chunk", "chunk__resource"
    ).filter(chunk__in=_candidate_chunks(user, scope))
    if not embeddings.exists():
        return []

    provider = get_provider()
    query_vector = provider.embed([query])[0]

    scored = []
    for entry in embeddings:
        if entry.model_name != provider.model or len(entry.vector) != len(query_vector):
            continue  # stale vector space; re-embedding is the pipeline's job
        similarity = cosine_similarity(query_vector, entry.vector)
        if similarity >= min_similarity:
            scored.append((similarity, entry.chunk))
    scored.sort(key=lambda pair: -pair[0])
    return [
        SearchResult(chunk=chunk, semantic_score=similarity)
        for similarity, chunk in scored[:limit]
    ]


def hybrid_search(user, query, scope=None, limit=None):
    """Fuse keyword and semantic lists with Reciprocal Rank Fusion."""
    limit = limit or max(
        getattr(settings, "SEARCH_SEMANTIC_TOP_K", 12),
        getattr(settings, "SEARCH_KEYWORD_TOP_K", 12),
    )
    keyword_results = keyword_search(user, query, scope)
    try:
        semantic_results = semantic_search(user, query, scope)
    except AIError:
        # Provider outages must not take search down: degrade to keyword-only.
        semantic_results = []

    rrf_k = 60
    fused = {}
    for index, result in enumerate(keyword_results, start=1):
        entry = fused.setdefault(result.chunk.pk, SearchResult(chunk=result.chunk))
        entry.keyword_rank = result.keyword_rank
        entry.fused_score += 1 / (rrf_k + index)
    for index, result in enumerate(semantic_results, start=1):
        entry = fused.setdefault(result.chunk.pk, SearchResult(chunk=result.chunk))
        entry.semantic_score = result.semantic_score
        entry.fused_score += 1 / (rrf_k + index)

    ranked = sorted(fused.values(), key=lambda r: -r.fused_score)[:limit]
    return [r for r in ranked if r.keyword_rank or r.semantic_score]


def build_snippet(chunk, query, window=90):
    """Escape a text window around the first matching term, with <mark>."""
    from django.utils.html import escape

    text = " ".join(chunk.text.split())
    terms = _terms(query)
    position = 0
    for term in terms:
        found = text.lower().find(term.lower())
        if found != -1:
            position = max(0, found - window // 3)
            break
    segment = text[position : position + window * 2]
    segment = escape(segment)
    for term in terms:
        pattern = re.compile(re.escape(escape(term)), re.IGNORECASE)
        segment = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", segment)
    prefix = "&hellip;" if position > 0 else ""
    suffix = "&hellip;" if position + window * 2 < len(text) else ""
    return f"{prefix}{segment}{suffix}"