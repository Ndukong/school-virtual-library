from unittest import mock

from django.core.files.base import ContentFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from ai.models import AIRequestLog
from ai.providers import get_provider
from ai.providers.base import AIError
from ai.providers.mock import MockAIProvider
from documents.dispatcher import enqueue
from documents.models import ChunkEmbedding, ProcessingJob
from documents.services import chunk_resource, embed_resource_chunks, extract_text
from library.models import Resource
from schools.models import School
from search.services import (
    build_snippet,
    cosine_similarity,
    hybrid_search,
    keyword_search,
    semantic_search,
)
from subjects.models import Subject

PASSWORD = "ComplexPass123!"


class SearchTestBase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")
        self.physics_a = Subject.objects.create(school=self.school_a, name="Physics")
        self.teacher_a = User.objects.create_user(
            "tcha", password=PASSWORD, role=User.Role.TEACHER, school=self.school_a
        )
        self.teacher_b = User.objects.create_user(
            "tchb", password=PASSWORD, role=User.Role.TEACHER, school=self.school_b
        )
        self.student_a = User.objects.create_user(
            "stua", password=PASSWORD, role=User.Role.STUDENT, school=self.school_a
        )

    def make_processed_resource(self, pages, title="Physics Notes",
                                school=None, uploader=None,
                                access_policy=Resource.AccessPolicy.SCHOOL,
                                subject=None,
                                embed=True):
        from documents.tests import build_pdf

        school = school or self.school_a
        uploader = uploader or (self.teacher_a if school == self.school_a else self.teacher_b)
        data = build_pdf(list(pages))
        resource = Resource(
            school=school, title=title, uploaded_by=uploader,
            resource_type=Resource.ResourceType.NOTES, access_policy=access_policy,
            subject=subject,
        )
        resource.file.save("doc.pdf", ContentFile(data), save=False)
        resource.original_filename = "doc.pdf"
        resource.file_size = len(data)
        resource.save()
        extract_text(resource)
        chunk_resource(resource)
        if embed:
            embed_resource_chunks(resource)
        return resource

    def create_corpus(self):
        """Shared fixture set used by scoping and view tests."""
        self.open_resource = self.make_processed_resource(
            ("Electromagnetic induction explains generators.", "Lenz's law gives direction."),
            title="EM Notes",
            subject=self.physics_a,
        )
        self.staff_resource = self.make_processed_resource(
            ("Confidential marking guidance text.",),
            title="Marking Guide",
            access_policy=Resource.AccessPolicy.TEACHERS_ONLY,
        )
        self.foreign_resource = self.make_processed_resource(
            ("Totally unique zebra physics content.",),
            title="Other School",
            school=self.school_b,
        )


class ProviderTests(TestCase):
    def test_mock_vectors_are_deterministic_and_normalised_shape(self):
        provider = get_provider()
        self.assertIsInstance(provider, MockAIProvider)
        vectors = provider.embed(["electric field", "electric field", "magnetic flux"])
        self.assertEqual(len(vectors), 3)
        self.assertEqual(vectors[0], vectors[1])
        self.assertNotEqual(vectors[0], vectors[2])
        self.assertTrue(all(len(v) == 16 for v in vectors))

    def test_cosine_similarity_basics(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [-1, 0]), -1.0)
        self.assertEqual(cosine_similarity([1], [1, 2]), 0.0)

    def test_factory_rejects_unknown_provider(self):
        with self.assertRaises(AIError):
            get_provider(kind="does_not_exist")

    def test_openai_compatible_requires_configuration(self):
        from ai.providers.openai_compat import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(api_key="", model="x")
        with self.assertRaises(AIError):
            provider.embed(["hello"])

    def test_usage_logged_on_success_and_failure(self):
        provider = get_provider()
        provider.embed(["one", "two"])
        self.assertTrue(
            AIRequestLog.objects.filter(provider="mock", kind="EMBED", ok=True, input_items=2).exists()
        )

        def boom(self, texts):
            raise RuntimeError("provider down")

        with mock.patch.object(MockAIProvider, "_embed_impl", boom):
            with self.assertRaises(RuntimeError):
                get_provider().embed(["three"])
        self.assertTrue(AIRequestLog.objects.filter(ok=False, error__icontains="provider down").exists())

    def test_http_failure_is_logged_and_raises_ai_error(self):
        from ai.providers.openai_compat import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(api_key="k", model="m")
        with override_settings(AI_BASE_URL="https://example.invalid/v1", AI_MAX_RETRIES=0):
            with mock.patch("urllib.request.urlopen", side_effect=OSError("no network")):
                with self.assertRaises(AIError):
                    provider.embed(["hello"])
        self.assertTrue(
            AIRequestLog.objects.filter(provider="openai_compatible", ok=False).exists()
        )


class EmbeddingPipelineTests(SearchTestBase):
    def test_embeddings_created_once_and_reused(self):
        resource = self.make_processed_resource(("Electromagnetic induction text.",), embed=False)
        stats_first = embed_resource_chunks(resource)
        self.assertEqual(stats_first["embedded"], resource.chunks.count())
        stats_second = embed_resource_chunks(resource)
        self.assertEqual(stats_second["embedded"], 0)
        self.assertEqual(stats_second["skipped_existing"], resource.chunks.count())
        self.assertEqual(ChunkEmbedding.objects.filter(chunk__resource=resource).count(),
                         resource.chunks.count())

    def test_model_change_reembeds(self):
        resource = self.make_processed_resource(("Induction content.",))
        old_count = ChunkEmbedding.objects.filter(
            chunk__resource=resource, model_name="mock-embed-small"
        ).count()
        self.assertEqual(old_count, resource.chunks.count())
        with override_settings(AI_EMBEDDING_MODEL="mock-embed-large"):
            stats = embed_resource_chunks(resource)
        self.assertEqual(stats["model"], "mock-embed-large")
        self.assertEqual(stats["embedded"], resource.chunks.count())
        self.assertFalse(
            ChunkEmbedding.objects.filter(
                chunk__resource=resource, model_name="mock-embed-small"
            ).exists()
        )

    def test_pipeline_chains_to_ready_via_embed(self):
        resource = self.make_processed_resource(("Motion chapter text.",), embed=False)
        with override_settings(DOCUMENTS_INLINE_PROCESSING=True):
            enqueue(resource, ProcessingJob.Step.EXTRACT)
            enqueue(resource, ProcessingJob.Step.CHUNK)
        resource.refresh_from_db()
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.READY)
        self.assertTrue(ChunkEmbedding.objects.filter(chunk__resource=resource).exists())
        self.assertTrue(
            ProcessingJob.objects.filter(
                resource=resource, step=ProcessingJob.Step.EMBED,
                status=ProcessingJob.Status.SUCCEEDED,
            ).exists()
        )


class SearchScopingTests(SearchTestBase):
    def setUp(self):
        super().setUp()
        self.create_corpus()

    def test_keyword_search_excludes_cross_school(self):
        results = keyword_search(self.teacher_a, "zebra")
        self.assertEqual(results, [])

    def test_keyword_search_excludes_teachers_only_from_students(self):
        self.assertEqual(keyword_search(self.student_a, "confidential marking"), [])
        self.assertNotEqual(keyword_search(self.teacher_a, "confidential marking"), [])

    def test_keyword_search_finds_visible_content(self):
        results = keyword_search(self.student_a, "electromagnetic induction")
        self.assertTrue(any(r.resource.pk == self.open_resource.pk for r in results))

    def test_semantic_search_respects_permissions(self):
        # Mock vectors carry no real semantics, so craft deterministic ones:
        # give the staff chunk exactly the query's vector. Permission-first
        # filtering must still hide it from students.
        from documents.models import ChunkEmbedding

        query = "marking guidance"
        provider = get_provider()
        query_vector = provider.embed([query])[0]
        chunk = self.staff_resource.chunks.first()
        ChunkEmbedding.objects.filter(chunk=chunk).update(
            vector=list(query_vector), dimensions=len(query_vector)
        )

        student_results = semantic_search(self.student_a, query)
        self.assertFalse(
            any(r.chunk.pk == chunk.pk for r in student_results)
        )
        teacher_results = semantic_search(self.teacher_a, query)
        self.assertTrue(any(r.chunk.pk == chunk.pk for r in teacher_results))

    def test_semantic_search_skips_stale_model_vectors(self):
        with override_settings(AI_EMBEDDING_MODEL="mock-embed-large"):
            results = semantic_search(self.student_a, "electromagnetic")
        self.assertEqual(results, [])  # all vectors stale; no mixed-space ranking

    def test_hybrid_fusion_merges_without_duplicates(self):
        results = hybrid_search(self.teacher_a, "electromagnetic induction")
        chunk_ids = [r.chunk.pk for r in results]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)))
        scores = [r.fused_score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_hybrid_degrades_to_keyword_when_provider_down(self):
        with mock.patch(
            "search.services.semantic_search", side_effect=AIError("provider down")
        ):
            results = hybrid_search(self.teacher_a, "electromagnetic induction")
        self.assertTrue(results)
        self.assertTrue(all(r.semantic_score is None for r in results))

    def test_scope_filters_narrow_results(self):
        results = keyword_search(
            self.student_a, "induction", scope={"subject": self.physics_a.pk}
        )
        self.assertTrue(results)
        foreign_subject = Subject.objects.create(school=self.school_b, name="Physics")
        results = keyword_search(
            self.student_a, "induction", scope={"subject": foreign_subject.pk}
        )
        self.assertEqual(results, [])

    def test_snippet_marks_matches_and_escapes(self):
        results = keyword_search(self.student_a, "induction")
        snippet = build_snippet(results[0].chunk, "induction")
        self.assertIn("<mark>", snippet)
        self.assertNotIn("<script", snippet)


class SearchViewTests(SearchTestBase):
    def setUp(self):
        super().setUp()
        self.create_corpus()

    def test_anonymous_redirected(self):
        response = Client().get(reverse("search"), {"q": "induction"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_results_page_for_student(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("search"), {"q": "induction"})
        self.assertContains(response, "EM Notes")
        self.assertNotContains(response, "Other School")

    def test_empty_query_renders_form_only(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("search"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "result(s)")

    def test_no_results_message(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("search"), {"q": "qqqqzzzz"})
        self.assertContains(response, "No results")


class KeywordRecallTests(SearchTestBase):
    """Regression: keyword search must not slice by row order (AGENTS #3)."""

    @override_settings(SEARCH_KEYWORD_TOP_K=12)
    def test_match_beyond_500_rows_is_still_found(self):
        from documents.models import DocumentChunk

        resource = self.make_processed_resource(
            ("filler",), title="Many chunks", embed=False
        )
        # Fill rows so the interesting match would previously sit beyond the
        # arbitrary id-ordered [:500] slice.
        DocumentChunk.objects.bulk_create([
            DocumentChunk(resource=resource, sequence=i, text="unrelated filler text")
            for i in range(2, 522)
        ])
        target = self.make_processed_resource(
            ("unique needle phrase that only appears here.",),
            title="Needle doc",
        )

        results = keyword_search(self.student_a, "unique needle phrase")
        self.assertTrue(any(r.chunk.resource_id == target.pk for r in results))
class PgvectorBackendTests(SimpleTestCase):
    def test_sql_ranks_in_database_with_placeholders(self):
        from search.backends import pg_semantic_ranking_sql

        sql, param_count = pg_semantic_ranking_sql([11, 22, 33], limit=12)
        self.assertIn("ORDER BY ce.embedding <-> %s", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertIn("chunk_id IN (%s, %s, %s)", sql)
        self.assertEqual(param_count, 3 + 2)

    def test_pg_path_disabled_on_sqlite(self):
        from search.backends import use_pgvector

        self.assertFalse(use_pgvector())

    def test_backfill_command_guidance_on_non_postgres(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("backfill_pg_vectors", stdout=out)
        self.assertIn("PostgreSQL", out.getvalue())
class EmbeddingQueryCacheTests(TestCase):
    def test_query_vector_cached_per_model_and_normalized(self):
        from django.core.cache import cache

        from search.services import _embed_query

        cache.clear()
        calls = {"n": 0}

        class CountingProvider:
            model = "test-model"

            def embed(self, texts):
                calls["n"] += 1
                return [[0.1, 0.2, 0.3, 0.4]]

        with mock.patch("search.services.get_provider", return_value=CountingProvider()):
            first = _embed_query("Electromagnetic induction")
            second = _embed_query("electromagnetic   INDUCTION")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(first[1], second[1])
        self.assertEqual(first[1], [0.1, 0.2, 0.3, 0.4])
class BenchmarkCommandTests(TestCase):
    def test_benchmark_reports_p50_p95(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("benchmark_search", chunks=20, iterations=3, stdout=out)
        output = out.getvalue()
        self.assertIn("p50=", output)
        self.assertIn("p95=", output)
        self.assertIn("keyword", output)
        self.assertIn("hybrid", output)
