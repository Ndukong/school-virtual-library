"""Search backend selection (WP5).

Semantic ranking lives behind one interface:
- PostgreSQL + pgvector: ORDER BY embedding <-> %s in SQL over the
  permission-filtered chunk id set (the vectors stay in the database; no
  full-corpus Python cosine).
- SQLite (dev/fallback): Python cosine over the permission-filtered set.

Permission filtering happens BEFORE either path via the shared candidate
queryset - ranking never widens the visible set.
"""

from django.conf import settings
from django.db import connection

PG_VECTOR_TABLE = "search_pg_chunk_vector"
PG_DISTANCE_OP = "ce.embedding <-> %s"


def use_pgvector():
    """True when the connected database can rank with pgvector."""
    if connection.vendor != "postgresql":
        return False
    return isinstance(getattr(settings, "SEARCH_PGVECTOR_DIM", 0), int) and (
        getattr(settings, "SEARCH_PGVECTOR_DIM", 0) > 0
    )


def pg_semantic_ranking_sql(chunk_ids, vector_param_placeholder="%s", limit=12):
    """Return (sql, param_count) for distance-ordered ranking.

    chunk_ids are already permission-filtered; ranks are computed in SQL so
    the index (HNSW on embedding) does the work, not Python.
    """
    chunk_ids = list(chunk_ids)
    if not chunk_ids:
        raise ValueError("chunk_ids must not be empty")
    placeholders = ", ".join([vector_param_placeholder] * (len(chunk_ids) + 2))
    sql = (
        f"SELECT ce.chunk_id, ce.embedding <-> {vector_param_placeholder} AS distance "
        f"FROM {PG_VECTOR_TABLE} ce "
        f"WHERE ce.chunk_id IN ({_list_placeholders(len(chunk_ids))}) "
        f"ORDER BY ce.embedding <-> {vector_param_placeholder} "
        f"LIMIT {vector_param_placeholder}"
    )
    return sql, len(chunk_ids) + 2


def _list_placeholders(count):
    return ", ".join(["%s"] * count)


def rank_chunks_pg(user, scope, query_vector, limit=None):
    """Rank the visible chunk ids by vector distance, in the database.

    Returns a plain list of chunk ids ordered nearest-first.
    """
    from django.db import connection

    from search.services import _candidate_chunks

    limit = limit or getattr(settings, "SEARCH_SEMANTIC_TOP_K", 12)
    chunk_ids = list(
        _candidate_chunks(user, scope).values_list("id", flat=True)
    )
    if not chunk_ids:
        return []
    sql, param_count = pg_semantic_ranking_sql(chunk_ids, limit=limit)
    vector_text = "[" + ",".join(str(float(v)) for v in query_vector) + "]"
    # Placeholders: distance (1), id-list (N), limit (1).
    params = [vector_text, *chunk_ids, limit]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    return [row[0] for row in rows]