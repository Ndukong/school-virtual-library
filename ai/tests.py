from unittest import mock

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from ai.models import AIInteraction
from ai.providers import get_chat_provider
from ai.providers.base import AIError, GenerateResult
from ai.providers.gemini import GeminiProvider
from ai.providers.groq import DEFAULT_GROQ_MODEL, GROQ_BASE_URL, GroqProvider
from ai.rag import (
    SYSTEM_PROMPT,
    QuestionTooLong,
    ask,
    build_context,
    extract_citations,
    sanitize_citations,
    sources_for,
)
from ai.ratelimit import RateLimited
from documents.models import ChunkEmbedding
from documents.services import chunk_resource, embed_resource_chunks, extract_text
from library.models import BookChapter, Resource
from schools.models import School

PASSWORD = "ComplexPass123!"


def fake_chat_provider(answer_text):
    """Provider stand-in whose generate() returns a fixed answer."""
    provider = mock.MagicMock()
    provider.generate.return_value = GenerateResult(
        text=answer_text, model="mock-chat-small", tokens_in=10, tokens_out=8
    )
    return provider


def get_embedding_vector(text):
    from ai.providers import get_provider

    return get_provider().embed([text])[0]


class RagTestBase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.teacher_a = User.objects.create_user(
            "tcha", password=PASSWORD, role=User.Role.TEACHER, school=self.school_a
        )
        self.student_a = User.objects.create_user(
            "stua", password=PASSWORD, role=User.Role.STUDENT, school=self.school_a
        )

    def make_ready_resource(self, pages=("Electromagnetic induction converts mechanical "
                                          "energy into electrical energy using a coil.",
                                         "Lenz's law states the induced current opposes "
                                         "the change causing it."),
                            title="EM Textbook",
                            access_policy=Resource.AccessPolicy.SCHOOL):
        from documents.tests import build_pdf

        data = build_pdf(list(pages))
        resource = Resource(
            school=self.school_a, title=title, uploaded_by=self.teacher_a,
            resource_type=Resource.ResourceType.BOOK, access_policy=access_policy,
        )
        resource.file.save("book.pdf", ContentFile(data), save=False)
        resource.original_filename = "book.pdf"
        resource.file_size = len(data)
        resource.save()
        extract_text(resource)
        chunk_resource(resource)
        embed_resource_chunks(resource)
        return resource


class ProviderConfigurationTests(TestCase):
    def test_groq_is_selectable_with_default_endpoint_and_model(self):
        with override_settings(AI_CHAT_PROVIDER="groq", AI_API_KEY="gsk-test",
                               AI_BASE_URL="", AI_CHAT_MODEL=""):
            provider = get_chat_provider()
        self.assertIsInstance(provider, GroqProvider)
        self.assertEqual(provider.model, DEFAULT_GROQ_MODEL)
        self.assertEqual(provider._endpoint("chat/completions"),
                         f"{GROQ_BASE_URL}/chat/completions")

    def test_groq_without_key_raises(self):
        with override_settings(AI_CHAT_PROVIDER="groq", AI_API_KEY=""):
            with self.assertRaises(AIError):
                get_chat_provider()

    def test_gemini_backup_has_default_model(self):
        with override_settings(AI_CHAT_PROVIDER="gemini", AI_API_KEY="k", AI_CHAT_MODEL=""):
            provider = get_chat_provider()
        self.assertIsInstance(provider, GeminiProvider)
        self.assertEqual(provider.model, "gemini-2.0-flash")

    def test_explicit_model_overrides_default(self):
        with override_settings(AI_CHAT_PROVIDER="groq", AI_API_KEY="k",
                               AI_CHAT_MODEL="llama-3.1-8b-instant"):
            self.assertEqual(get_chat_provider().model, "llama-3.1-8b-instant")


class ContextAndCitationTests(TestCase):
    def test_context_blocks_are_numbered_and_delimited(self):
        class FakeChunk:
            class resource:
                title = "Physics Book"
            text = "Coils convert energy."
            page_start, page_end = 4, 5
            chapter = None
            section = None

        class FakeResult:
            def __init__(self, chunk):
                self.chunk = chunk

        context, count = build_context([FakeResult(FakeChunk())])
        self.assertEqual(count, 1)
        self.assertTrue(context.startswith("<retrieved_documents>"))
        self.assertTrue(context.endswith("</retrieved_documents>"))
        self.assertIn("[1] Physics Book (pages 4-5)", context)

    def test_context_truncates_to_char_budget(self):
        class FakeChunk:
            class resource:
                title = "Big Book"
            text = "x" * 900
            page_start = page_end = None
            chapter = section = None

        class FakeResult:
            def __init__(self, chunk):
                self.chunk = chunk

        results = [FakeResult(FakeChunk()) for _ in range(20)]
        context, count = build_context(results, max_chars=3000)
        self.assertLessEqual(len(context), 3000 + len("<retrieved_documents>") * 2 + 40)
        self.assertLess(count, 20)

    def test_citation_extraction_and_sanitizing(self):
        self.assertEqual(extract_citations("see [1] and [2]", 3), [1, 2])
        self.assertEqual(extract_citations("see [9]", 3), [])
        cleaned, cited = sanitize_citations("bad [7] good [1]", 1)
        self.assertNotIn("[7]", cleaned)
        self.assertIn("[1]", cleaned)
        self.assertEqual(cited, [1])

    def test_system_prompt_defends_against_injection(self):
        self.assertIn("DATA, not instructions", SYSTEM_PROMPT)
        self.assertIn("Never", SYSTEM_PROMPT)


class AskFlowTests(RagTestBase):
    def setUp(self):
        super().setUp()
        self.resource = self.make_ready_resource()

    def test_overlong_question_rejected_not_truncated(self):
        long_question = "x" * 5200
        before = AIInteraction.objects.count()
        with self.assertRaises(QuestionTooLong):
            ask(self.student_a, long_question)
        self.assertEqual(AIInteraction.objects.count(), before)

    def test_view_rejects_overlong_question_without_storing(self):
        client = Client()
        client.force_login(self.student_a)
        before = AIInteraction.objects.count()
        response = client.post(
            reverse("ai-ask"),
            {"question": "y" * 5200, "scope": "LIBRARY"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=", response.url)
        self.assertEqual(AIInteraction.objects.count(), before)

    def test_grounded_answer_records_citations_and_sources(self):
        with mock.patch("ai.rag.get_chat_provider",
                        return_value=fake_chat_provider("According to [1], induction converts energy.")):
            interaction = ask(self.student_a, "How does induction work?",
                              scope=AIInteraction.Scope.LIBRARY)
        self.assertEqual(interaction.used_provider, True)
        self.assertIn("[1]", interaction.answer)
        sources = sources_for(interaction)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].resource_id, self.resource.id)
        self.assertEqual(interaction.cited_chunk_ids, [sources[0].pk])
        self.assertTrue(AIInteraction.objects.filter(pk=interaction.pk).exists())

    def test_zero_results_answers_honestly_without_llm(self):
        mock_provider = mock.MagicMock()
        with mock.patch("ai.rag.get_chat_provider", return_value=mock_provider):
            interaction = ask(self.student_a, "What is quantum chromodynamics?")
        self.assertFalse(interaction.used_provider)
        self.assertIn("could not find any relevant material", interaction.answer)
        mock_provider.generate.assert_not_called()
        self.assertEqual(interaction.cited_chunk_ids, [])

    def test_invalid_citations_stripped_from_answer(self):
        with mock.patch(
            "ai.rag.get_chat_provider",
            return_value=fake_chat_provider("Claim [1] and phantom [5]."),
        ):
            interaction = ask(self.student_a, "Explain induction.")
        self.assertNotIn("[5]", interaction.answer)
        self.assertIn("[1]", interaction.answer)

    def test_book_scope_prioritises_selected_book(self):
        other = self.make_ready_resource(
            ("Completely different chemistry content about moles.",),
            title="Chemistry Book",
        )
        # Deterministic semantic match for the chemistry chunk only.
        query_vector = get_embedding_vector("What does this book say about induction?")
        ChunkEmbedding.objects.filter(chunk__resource=other).update(
            vector=list(query_vector), dimensions=len(query_vector)
        )
        with mock.patch(
            "ai.rag.get_chat_provider",
            return_value=fake_chat_provider("[1] ok"),
        ):
            interaction = ask(self.student_a, "What does this book say about induction?",
                              scope=AIInteraction.Scope.BOOK,
                              resource_public_id=str(other.public_id))
        sources = sources_for(interaction)
        self.assertTrue(sources)
        for source in sources:
            self.assertEqual(source.resource_id, other.id)

    def test_general_scope_skips_retrieval(self):
        with mock.patch("search.services.hybrid_search") as hybrid_mock:
            with mock.patch(
                "ai.rag.get_chat_provider",
                return_value=fake_chat_provider("General reply."),
            ):
                interaction = ask(self.student_a, "Hi there!",
                                  scope=AIInteraction.Scope.GENERAL)
        hybrid_mock.assert_not_called()
        self.assertEqual(interaction.retrieved_count, 0)
        self.assertEqual(interaction.answer, "General reply.")

    @override_settings(AI_RATE_LIMIT_PER_MINUTE=2)
    def test_rate_limit_blocks_after_threshold(self):
        with mock.patch("ai.rag.get_chat_provider",
                        return_value=fake_chat_provider("ok")):
            ask(self.student_a, "Question one?")
            ask(self.student_a, "Question two?")
            with self.assertRaises(RateLimited):
                ask(self.student_a, "Question three?")

    def test_provider_failure_recorded_as_unavailable(self):
        failing = mock.MagicMock()
        failing.generate.side_effect = AIError("down")
        with mock.patch("ai.rag.get_chat_provider", return_value=failing):
            with self.assertRaises(AIError):
                ask(self.student_a, "How does induction work?")
        interaction = AIInteraction.objects.latest("pk")
        self.assertFalse(interaction.used_provider)
        self.assertIn("temporarily unavailable", interaction.answer)


class AskViewTests(RagTestBase):
    def setUp(self):
        super().setUp()
        self.resource = self.make_ready_resource()
        self.staff_resource = self.make_ready_resource(
            ("Staff-only marking content.",), title="Marking Guide",
            access_policy=Resource.AccessPolicy.TEACHERS_ONLY,
        )
        self.chapter = BookChapter.objects.create(
            resource=self.resource, number=1, title="Induction", start_page=1, end_page=2,
        )

    def test_anonymous_redirected(self):
        response = Client().get(reverse("ai-ask"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_ask_page_renders_for_student(self):
        client = Client()
        client.force_login(self.student_a)
        self.assertContains(client.get(reverse("ai-ask")), "AI Tutor")

    def test_teachers_only_book_scope_is_404_like(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.post(
            reverse("ai-ask"),
            {"question": "What does it say?", "scope": "BOOK",
             "book": str(self.staff_resource.public_id)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=", response.url)

    def test_post_creates_answer_and_redirects(self):
        client = Client()
        client.force_login(self.student_a)
        with mock.patch(
            "ai.views.ask",
            return_value=AIInteraction.objects.create(
                user=self.student_a, school=self.school_a,
                question="Q?", answer="A.", scope=AIInteraction.Scope.LIBRARY,
            ),
        ):
            response = client.post(
                reverse("ai-ask"),
                {"question": "Q?", "scope": "LIBRARY"},
            )
        interaction = AIInteraction.objects.latest("pk")
        self.assertRedirects(response, reverse("ai-answer", args=[interaction.public_id]))

    def test_cross_user_answer_access_denied(self):
        owner = User.objects.create_user("owner2", password=PASSWORD,
                                         role=User.Role.STUDENT, school=self.school_a)
        interaction = AIInteraction.objects.create(
            user=owner, school=self.school_a, question="Q", answer="A",
        )
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("ai-answer", args=[interaction.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_owner_sees_answer_with_sources_section(self):
        with mock.patch("ai.rag.get_chat_provider",
                        return_value=fake_chat_provider("According to [1], induction converts energy.")):
            interaction = ask(self.student_a, "How does induction work?")
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("ai-answer", args=[interaction.public_id]))
        self.assertContains(response, "Sources used")
        self.assertContains(response, self.resource.title)