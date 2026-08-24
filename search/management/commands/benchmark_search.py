"""Search latency benchmark (WP5).

Seeds a synthetic corpus for a school and reports p50/p95 latency for the
keyword, semantic and hybrid searches so regressions are visible. Uses the
configured embedding provider (mock in local dev, or a real provider).
"""

import random
import time
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from documents.models import DocumentChunk
from library.models import Resource
from schools.models import School

_WORDS = [
    "physics", "potential", "energy", "kinetic", "force", "motion",
    "wave", "charge", "current", "question", "answer", "formula",
]


class Command(BaseCommand):
    help = "Report p50/p95 search latency against a seeded corpus."

    def add_arguments(self, parser):
        parser.add_argument("--school-pk", type=int, default=None)
        parser.add_argument("--chunks", type=int, default=200)
        parser.add_argument("--iterations", type=int, default=30)
        parser.add_argument("--query", default="potential energy physics")

    @transaction.atomic
    def handle(self, *args, **options):
        from documents.services import embed_resource_chunks
        from search.services import hybrid_search, keyword_search, semantic_search

        school, teacher, student, resource = self._seed(options)
        try:
            embed_resource_chunks(resource)
            query = options["query"]
            suites = {
                "keyword": lambda: keyword_search(student, query),
                "semantic": lambda: semantic_search(student, query),
                "hybrid": lambda: hybrid_search(student, query),
            }
            for name, fn in suites.items():
                p50, p95 = self._measure(fn, options["iterations"])
                self.stdout.write(
                    f"{name} p50={p50 * 1000:.3f}ms p95={p95 * 1000:.3f}ms "
                    f"(chunks={options['chunks']}, iterations={options['iterations']})"
                )
        finally:
            self._teardown(resource, teacher, student, school, keep_school=bool(options["school_pk"]))

    def _seed(self, options):
        if options["school_pk"]:
            school = School.objects.filter(pk=options["school_pk"]).first()
            if school is None:
                raise CommandError(f"No school with pk {options['school_pk']}.")
        else:
            school = School.objects.create(name=f"Benchmark {uuid.uuid4().hex[:8]}")
        username = f"bench_{uuid.uuid4().hex[:8]}"
        teacher = User.objects.create_user(
            username + "_t", password="ComplexPass123!",
            role=User.Role.TEACHER, school=school,
        )
        student = User.objects.create_user(
            username + "_s", password="ComplexPass123!",
            role=User.Role.STUDENT, school=school,
        )
        resource = Resource.objects.create(
            school=school, title="Benchmark corpus", uploaded_by=teacher,
            resource_type=Resource.ResourceType.NOTES,
        )
        rng = random.Random(42)  # deterministic corpus
        for index in range(options["chunks"]):
            DocumentChunk.objects.create(
                resource=resource,
                sequence=index,
                text=" ".join(rng.choice(_WORDS) for _ in range(40)),
            )
        return school, teacher, student, resource

    def _measure(self, fn, iterations):
        latencies = []
        for _ in range(max(iterations, 1)):
            start = time.perf_counter()
            fn()
            latencies.append(time.perf_counter() - start)
        latencies.sort()

        def percentile(quantile):
            return latencies[int(round((len(latencies) - 1) * quantile))]

        return percentile(0.50), percentile(0.95)

    def _teardown(self, resource, teacher, student, school, keep_school):
        resource.delete()
        User.objects.filter(pk__in=[teacher.pk, student.pk]).delete()
        if not keep_school:
            from ai.models import AIRequestLog

            AIRequestLog.objects.filter(school=school).delete()
            school.delete()
