"""Conditional pgvector support (WP5).

On PostgreSQL this migration creates the vector table (HNSW index) that backs
``ORDER BY distance`` semantic ranking. On SQLite/other backends it is a
no-op, which keeps the dev suite db-agnostic. The python fallback ranking
(ChunkEmbedding.vector JSON) is untouched and remains the source for the
``backfill_pg_vectors`` command.
"""

from django.db import migrations

PG_VECTOR_TABLE = "search_pg_chunk_vector"


def _is_postgres(apps, schema_editor):
    return schema_editor.connection.vendor == "postgresql"


def create_pgvector(apps, schema_editor):
    if not _is_postgres(apps, schema_editor):
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    schema_editor.execute(
        f"CREATE TABLE {PG_VECTOR_TABLE} ("
        "chunk_id bigint PRIMARY KEY "
        "REFERENCES documents_documentchunk(id) ON DELETE CASCADE, "
        "embedding vector(768)"
        ")"
    )
    schema_editor.execute(
        f"CREATE INDEX {PG_VECTOR_TABLE}_hnsw ON {PG_VECTOR_TABLE} "
        "USING hnsw (embedding vector_l2_ops)"
    )


def drop_pgvector(apps, schema_editor):
    if not _is_postgres(apps, schema_editor):
        return
    schema_editor.execute(f"DROP TABLE IF EXISTS {PG_VECTOR_TABLE}")


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_extractedpage_needs_ocr_extractedpage_ocr_at_and_more"),
    ]
    operations = [
        migrations.RunPython(create_pgvector, drop_pgvector),
    ]