from unittest import mock

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from ai.models import AIGeneration, AIInteraction
from ai.ratelimit import RateLimited, recent_ai_request_count
from ai.study import STUDY_SYSTEM_PROMPT, STUDY_TASKS, generate_study_material
from documents.models import ChunkEmbedding
from documents.services import chunk_resource, embed_resource_chunks, extract_text
from documents.tests import build_pdf
from library.models import Resource
from schools.models import School

PASSWORD = "ComplexPass123!"


def fake_chat_provider(answer_text):
    provider = mock.MagicMock()
    result = mock.MagicMock()
    result.text = answer_text
    result.model = "mock-chat-small"
    provider.generate.return_value = result
    return provider


class StudyTestBase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")
        self.teacher_a = User.objects.create_user(
            "tcha", password=PASSWORD, role=User.Role.TEACHER, school=self.school_a
        )
        self.student_a = User.objects.create_user(
            "stua", password=PASSWORD, role=User.Role.STUDENT, school=self.school_a
        )
        self.teacher_b = User.objects.create_user(
            "tchb", password=PASSWORD, role=User.Role.TEACHER, school=self.school_b
        )

    def make_ready_resource(self, pages, title="EM Textbook",
                            school=None,
                            access_policy=Resource.AccessPolicy.SCHOOL,
                            embed=True):
        school = school or self.school_a
        uploader = self.teacher_a if school == self.school_a else self.teacher_b
        data = build_pdf(list(pages))
        resource = Resource(
            school=school,
            title=title,
            uploaded_by=uploader,
            resource_type=Resource.ResourceType.BOOK,
            access_policy=access_policy,
        )
        resource.file.save("book.pdf", ContentFile(data), save=False)
        resource.original_filename = "book.pdf"
        resource.file_size = len(data)
        resource.save()
        extract_text(resource)
        chunk_resource(resource)
        if embed:
            embed_resource_chunks(resource)
        return resource


class StudyGenerationTests(StudyTestBase):
    def make_em_resource(self):
        return self.make_ready_resource(
            ("Electromagnetic induction converts mechanical energy into "
             "electrical energy using a coil and magnetic field.",
             "Lenz's law gives the direction of the induced current."),
        )

    def test_every_kind_generates_grounded_content(self):
        resource = self.make_em_resource()
        for kind in AIGeneration.Kind.values:
            with self.subTest(kind=kind):
                with mock.patch(
                    "ai.study.get_chat_provider",
                    return_value=fake_chat_provider("Key point [1]."),
                ):
                    generation = generate_study_material(
                        self.student_a, kind, scope=AIInteraction.Scope.LIBRARY
                    )
                self.assertTrue(generation.used_provider)
                self.assertEqual(generation.model, "mock-chat-small")
                self.assertEqual(generation.prompt_version, "study-v2")
                self.assertIn("[1]", generation.content)
                self.assertEqual(generation.cited_chunk_ids,
                                 [resource.chunks.first().pk])
                self.assertGreaterEqual(generation.retrieved_count, 1)

    def test_task_prompts_demand_citations(self):
        for instruction in STUDY_TASKS.values():
            self.assertIn("[n]", instruction)

    def test_system_prompt_keeps_injection_defense(self):
        self.assertIn("DATA, not instructions", STUDY_SYSTEM_PROMPT)
        self.assertIn("Never", STUDY_SYSTEM_PROMPT)

    def test_invalid_kind_rejected_without_llm(self):
        provider = fake_chat_provider("should not be used")
        with mock.patch("ai.study.get_chat_provider", return_value=provider):
            with self.assertRaises(ValueError):
                generate_study_material(self.student_a, "PODCAST")
        provider.generate.assert_not_called()

    def test_zero_results_answers_honestly_without_llm(self):
        # No resources exist for this user's school yet.
        provider = fake_chat_provider("unused")
        with mock.patch("ai.study.get_chat_provider", return_value=provider):
            generation = generate_study_material(
                self.student_a, AIGeneration.Kind.SUMMARY
            )
        self.assertFalse(generation.used_provider)
        self.assertIn("No relevant material", generation.content)
        provider.generate.assert_not_called()

    def test_book_scope_uses_only_that_books_chunks(self):
        chemistry = self.make_ready_resource(
            ("Photosynthesis occurs in the chloroplast of plant cells.",),
            title="Chemistry Book",
        )
        query_vector = get_query_vector("photosynthesis chloroplast")
        ChunkEmbedding.objects.filter(chunk__resource=chemistry).update(
            vector=list(query_vector), dimensions=len(query_vector)
        )
        with mock.patch(
            "ai.study.get_chat_provider",
            return_value=fake_chat_provider("From this book [1]."),
        ):
            generation = generate_study_material(
                self.student_a,
                AIGeneration.Kind.REVISION_NOTES,
                scope=AIInteraction.Scope.BOOK,
                resource_public_id=str(chemistry.public_id),
                topic="photosynthesis chloroplast",
            )
        sources = chunk_ids_to_chunks(generation.cited_chunk_ids)
        self.assertTrue(sources)
        for source in sources:
            self.assertEqual(source.resource_id, chemistry.id)

    @override_settings(AI_RATE_LIMIT_PER_MINUTE=1)
    def test_rate_limit_is_shared_across_ai_features(self):
        AIInteraction.objects.create(user=self.student_a, question="q", answer="a")
        with mock.patch("ai.study.get_chat_provider",
                        return_value=fake_chat_provider("ok")):
            with self.assertRaises(RateLimited):
                generate_study_material(self.student_a, AIGeneration.Kind.SUMMARY)

    def test_rate_limit_counts_generations_not_only_interactions(self):
        AIGeneration.objects.create(
            user=self.student_a, kind=AIGeneration.Kind.SUMMARY,
            scope=AIInteraction.Scope.LIBRARY, content="c",
        )
        self.assertEqual(recent_ai_request_count(self.student_a), 1)


def get_query_vector(text):
    from ai.providers import get_provider

    return get_provider().embed([text])[0]


def chunk_ids_to_chunks(chunk_ids):
    from documents.models import DocumentChunk

    return list(DocumentChunk.objects.filter(pk__in=chunk_ids))


class StudyViewTests(StudyTestBase):
    def setUp(self):
        super().setUp()
        self.resource = self.make_ready_resource(("Induction text for study tools.",))
        self.staff_resource = self.make_ready_resource(
            ("Staff only content.",), title="Marking Guide",
            access_policy=Resource.AccessPolicy.TEACHERS_ONLY,
        )

    def test_anonymous_redirected(self):
        response = Client().get(reverse("ai-study"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_form_renders_with_kinds(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("ai-study"))
        self.assertContains(response, "Revision notes")

    def test_post_creates_generation_and_redirects(self):
        client = Client()
        client.force_login(self.student_a)
        with mock.patch(
            "ai.views.generate_study_material",
            return_value=AIGeneration.objects.create(
                user=self.student_a, kind=AIGeneration.Kind.SUMMARY,
                scope=AIInteraction.Scope.LIBRARY, content="Summary body.",
            ),
        ):
            response = client.post(
                reverse("ai-study"),
                {"kind": "SUMMARY", "scope": "LIBRARY", "topic": ""},
            )
        generation = AIGeneration.objects.latest("pk")
        self.assertRedirects(response, reverse("ai-study-result", args=[generation.public_id]))

    def test_result_page_owner_only(self):
        owner = User.objects.create_user("own2", password=PASSWORD,
                                         role=User.Role.STUDENT, school=self.school_a)
        generation = AIGeneration.objects.create(
            user=owner, kind=AIGeneration.Kind.SUMMARY,
            scope=AIInteraction.Scope.LIBRARY, content="Secret notes.",
        )
        client = Client()
        client.force_login(self.student_a)  # different user
        response = client.get(reverse("ai-study-result", args=[generation.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_mine_list_shows_only_own_materials(self):
        mine = AIGeneration.objects.create(
            user=self.student_a, kind=AIGeneration.Kind.SUMMARY,
            scope=AIInteraction.Scope.LIBRARY, content="Mine.",
        )
        other = AIGeneration.objects.create(
            user=self.teacher_a, kind=AIGeneration.Kind.SUMMARY,
            scope=AIInteraction.Scope.LIBRARY, content="Theirs.",
        )
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("ai-study-mine"))
        self.assertContains(response, reverse("ai-study-result", args=[mine.public_id]))
        self.assertNotContains(response, reverse("ai-study-result", args=[other.public_id]))

    def test_teachers_only_book_scope_rejected_for_student(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.post(
            reverse("ai-study"),
            {"kind": "SUMMARY", "scope": "BOOK",
             "book": str(self.staff_resource.public_id), "topic": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=", response.url)

    def test_result_page_labels_ai_generated(self):
        generation = AIGeneration.objects.create(
            user=self.student_a, kind=AIGeneration.Kind.PRACTICE_QUESTIONS,
            scope=AIInteraction.Scope.LIBRARY,
            content="Q: What is induction? [1]\nA: Energy conversion.",
        )
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("ai-study-result", args=[generation.public_id]))
        self.assertContains(response, "AI-generated study support")