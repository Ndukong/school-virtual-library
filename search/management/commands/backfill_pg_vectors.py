"""Backfill pgvector rows from the JSON ChunkEmbedding storage (WP5).

Run on PostgreSQL after enabling pgvector; returns a count. On other
backends it prints guidance and exits 0.
"""

from django.core.management.base import BaseCommand
from django.db import connection

from search.backends import PG_VECTOR_TABLE, use_pgvector


class Command(BaseCommand):
    help = "Copy stored chunk vectors into the pgvector table."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=500)

    def handle(self, *args, **options):
        if not use_pgvector():
            self.stdout.write(
                "pgvector ranking needs the search migration applied on "
                "PostgreSQL; nothing to backfill here."
            )
            return
        from documents.models import ChunkEmbedding

        rows = ChunkEmbedding.objects.all()
        inserted = 0
        batch = []
        for entry in rows.iterator(chunk_size=options["batch"]):
            batch.append(entry)
            if len(batch) >= options["batch"]:
                inserted += self._insert(batch)
                batch = []
        if batch:
            inserted += self._insert(batch)
        self.stdout.write(self.style.SUCCESS(f"Backfilled {inserted} vector row(s)."))

    def _insert(self, entries):
        params = []
        values = []
        for entry in entries:
            vector_text = "[" + ",".join(str(float(v)) for v in entry.vector) + "]"
            values.append("(%s, %s::vector)")
            params.extend([entry.chunk_id, vector_text])
        sql = (
            f"INSERT INTO {PG_VECTOR_TABLE} (chunk_id, embedding) VALUES "
            + ", ".join(values)
            + " ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
        return len(entries)