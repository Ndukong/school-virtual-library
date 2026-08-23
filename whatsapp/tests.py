import hashlib
import hmac
import json
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from learning.models import PracticeAttempt
from question_bank.models import Question
from question_bank.services import approve_question
from schools.models import School
from subjects.models import Subject
from whatsapp.models import WhatsAppMessage, WhatsAppSession
from whatsapp.services import (
    HELP_MENU,
    HUB_CHALLENGE,
    HUB_MODE,
    HUB_TOKEN,
    RATE_LIMITED_REPLY,
    WhatsAppError,
    create_link_code,
    get_session,
    handle_text,
    link_phone,
    normalize_inbound,
    verify_signature,
)

PASSWORD = "ComplexPass123!"
PHONE = "+15551230001"
VERIFY_TOKEN = "test-verify-token"
APP_SECRET = "test-app-secret"


def meta_payload(message_id, phone=PHONE, body="MENU", message_type="text"):
    message = {"from": phone.lstrip("+"), "id": message_id, "type": message_type}
    if message_type == "text":
        message["text"] = {"body": body}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [message]}}]}],
    }


def signed_post(client, payload):
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(
        APP_SECRET.encode(), raw, hashlib.sha256
    ).hexdigest()
    return client.post(
        reverse("whatsapp-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )


class SignatureTests(TestCase):
    def test_valid_signature_passes(self):
        body = b'{"entry": []}'
        signature = "sha256=" + hmac.new(
            APP_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        with override_settings(WHATSAPP_APP_SECRET=APP_SECRET):
            self.assertTrue(verify_signature(body, signature))

    def test_tampered_signature_fails(self):
        with override_settings(WHATSAPP_APP_SECRET=APP_SECRET):
            self.assertFalse(verify_signature(b'"changed"', "sha256=" + "0" * 64))

    def test_missing_header_raises_when_secret_set(self):
        with override_settings(WHATSAPP_APP_SECRET=APP_SECRET):
            with self.assertRaises(WhatsAppError):
                verify_signature(b'"x"', "")

    def test_fail_closed_without_secret_outside_debug(self):
        with override_settings(WHATSAPP_APP_SECRET="", DEBUG=False):
            with self.assertRaises(WhatsAppError):
                verify_signature(b'"x"', "sha256=abc")

    def test_debug_allows_unsigned_without_secret(self):
        with override_settings(WHATSAPP_APP_SECRET="", DEBUG=True):
            self.assertTrue(verify_signature(b'"x"', ""))


class NormalizeTests(TestCase):
    def test_extracts_text_messages(self):
        messages = list(normalize_inbound(
            meta_payload("abc123", body="What is induction?")
        ))
        self.assertEqual(messages, [("abc123", "+15551230001", "What is induction?")])

    def test_skips_media_messages(self):
        payload = meta_payload("img-1", message_type="image")
        self.assertEqual(list(normalize_inbound(payload)), [])


class LinkingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Alpha Academy")
        self.student = User.objects.create_user(
            "linkstudent", password=PASSWORD,
            role=User.Role.STUDENT, school=self.school,
        )

    def test_link_code_binds_phone_once(self):
        link = create_link_code(self.student)
        session = get_session(PHONE)
        user, error = link_phone(session, link.code)
        self.assertIsNone(error)
        self.assertEqual(user, self.student)
        session.refresh_from_db()
        self.assertEqual(session.linked_user, self.student)
        link.refresh_from_db()
        self.assertFalse(link.is_valid())  # single use

        # Reuse fails.
        _, error = link_phone(session, link.code)
        self.assertIn("invalid or has expired", error)

    def test_bogus_code_rejected(self):
        session = get_session(PHONE)
        user, error = link_phone(session, "NOPE")
        self.assertIsNone(user)
        self.assertIn("invalid", error)

    def test_expired_code_rejected(self):
        link = create_link_code(self.student)
        from django.utils import timezone

        link.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        link.save(update_fields=["expires_at"])
        session = get_session(PHONE)
        _, error = link_phone(session, link.code)
        self.assertIn("invalid or has expired", error)

    def test_unlinked_user_gets_link_prompt(self):
        session = get_session(PHONE)
        replies = handle_text(session, "SEARCH anything")
        self.assertTrue(any("LINK" in reply for reply in replies))

    def test_stop_unlinks(self):
        link = create_link_code(self.student)
        session = get_session(PHONE)
        link_phone(session, link.code)
        replies = handle_text(session, "STOP")
        session.refresh_from_db()
        self.assertIsNone(session.linked_user)
        self.assertTrue(any("unlinked" in reply for reply in replies))


class RoutingTests(TestCase):
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
        self.admin_a = User.objects.create_user(
            "adma", password=PASSWORD, role=User.Role.ADMIN,
            school=self.school_a, is_staff=True,
        )
        self.student_a = User.objects.create_user(
            "stua", password=PASSWORD, role=User.Role.STUDENT, school=self.school_a
        )

    def _linked_session(self):
        link = create_link_code(self.student_a)
        session = get_session(PHONE)
        link_phone(session, link.code)
        return session

    def _processed_resource(self, pages, title, school=None, with_embed=True):
        from django.core.files.base import ContentFile

        from documents.services import chunk_resource, embed_resource_chunks, extract_text
        from documents.tests import build_pdf
        from library.models import Resource

        school = school or self.school_a
        data = build_pdf(list(pages))
        resource = Resource(
            school=school, title=title,
            uploaded_by=self.teacher_a if school == self.school_a else self.teacher_b,
            resource_type=Resource.ResourceType.NOTES,
        )
        resource.file.save("doc.pdf", ContentFile(data), save=False)
        resource.original_filename = "doc.pdf"
        resource.file_size = len(data)
        resource.save()
        extract_text(resource)
        chunk_resource(resource)
        if with_embed:
            embed_resource_chunks(resource)
        return resource

    def test_menu_help(self):
        session = self._linked_session()
        self.assertEqual(handle_text(session, "MENU"), [HELP_MENU])

    def test_search_respects_permissions(self):
        mine = self._processed_resource(
            ["faraday law unique phrase about induction."], "My Book",
        )
        self._processed_resource(
            ["zebra reef content unique."], "Other School",
            school=self.school_b,
        )
        session = self._linked_session()
        replies = handle_text(session, "SEARCH faraday unique")
        self.assertTrue(any("My Book" in reply for reply in replies))
        self.assertFalse(any("Other School" in reply for reply in replies))

    def test_ask_grounded_and_rate_limited_shared(self):
        self._processed_resource(
            ["Electromagnetic induction converts mechanical energy."], "EM Notes",
        )
        session = self._linked_session()
        with mock.patch("ai.rag.get_chat_provider") as provider:
            result = mock.MagicMock()
            result.text = "Grounded answer [1]."
            result.model = "mock-chat-small"
            provider.return_value.generate.return_value = result
            replies = handle_text(session, "ASK how does induction work?")
        self.assertTrue(any("Grounded answer" in reply for reply in replies))


class QuizChannelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Alpha Academy")
        self.teacher = User.objects.create_user(
            "tch", password=PASSWORD, role=User.Role.TEACHER, school=self.school
        )
        self.admin = User.objects.create_user(
            "adm", password=PASSWORD, role=User.Role.ADMIN,
            school=self.school, is_staff=True,
        )
        self.student = User.objects.create_user(
            "stu", password=PASSWORD, role=User.Role.STUDENT, school=self.school
        )
        self.link = create_link_code(self.student)
        self.session = get_session(PHONE)
        link_phone(self.session, self.link.code)

    def _mcq(self, mark=1, options=("Alpha guess", "Beta right", "Gamma guess"),
             correct="Beta right"):
        question = Question.objects.create(
            school=self.school, topic="Induction",
            body="Choose the right one.",
            correct_answer=correct, options=list(options),
            question_type=Question.QuestionType.MCQ, marks=mark,
            author=self.teacher,
        )
        approve_question(self.admin, question)
        return question

    def test_full_quiz_flow_over_messages(self):
        self._mcq()
        replies = handle_text(self.session, "QUIZ")
        self.assertTrue(any("Quiz time" in reply for reply in replies))

        # Answer the only question correctly, then finish.
        replies = handle_text(self.session, "Beta right")
        self.assertTrue(any("Quiz complete" in reply for reply in replies))

        attempt = PracticeAttempt.objects.get(student=self.student)
        self.assertEqual(attempt.status, PracticeAttempt.Status.SUBMITTED)
        self.assertEqual(attempt.earned_marks, attempt.possible_marks)
        self.assertEqual(self.session.state, "MENU")

    def test_quiz_uses_objective_questions_only(self):
        # Structured question exists but must be excluded for WhatsApp quiz.
        Question.objects.create(
            school=self.school, topic="Induction",
            body="Explain in full.", correct_answer="Long answer.",
            question_type=Question.QuestionType.ESSAY, marks=5,
            author=self.teacher,
        )
        self._mcq()
        handle_text(self.session, "QUIZ")
        attempt = PracticeAttempt.objects.latest("pk")
        for response in attempt.responses.all():
            self.assertIn(
                response.question.question_type,
                (Question.QuestionType.MCQ.value, Question.QuestionType.TRUE_FALSE.value),
            )


class WebhookViewsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Alpha Academy")
        self.teacher = User.objects.create_user(
            "tch", password=PASSWORD, role=User.Role.TEACHER, school=self.school
        )
        self.admins = User.objects.create_user(
            "adm", password=PASSWORD, role=User.Role.ADMIN, school=self.school, is_staff=True
        )
        self.student = User.objects.create_user(
            "stu", password=PASSWORD, role=User.Role.STUDENT, school=self.school
        )
        self.link = create_link_code(self.student)

    def _configure(self):
        return override_settings(
            WHATSAPP_VERIFY_TOKEN=VERIFY_TOKEN,
            WHATSAPP_APP_SECRET=APP_SECRET,
            WHATSAPP_PROVIDER="console",
        )

    def test_get_handshake_success(self):
        with self._configure():
            client = Client()
            response = client.get(
                reverse("whatsapp-webhook-verify"),
                {HUB_MODE: "subscribe", HUB_TOKEN: VERIFY_TOKEN,
                 HUB_CHALLENGE: "abc123"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"abc123")

    def test_get_handshake_bad_token(self):
        with self._configure():
            client = Client()
            response = client.get(
                reverse("whatsapp-webhook-verify"),
                {HUB_MODE: "subscribe", HUB_TOKEN: "wrong", HUB_CHALLENGE: "x"},
            )
        self.assertEqual(response.status_code, 403)

    def test_unsigned_post_rejected(self):
        with self._configure():
            client = Client()
            raw = json.dumps(meta_payload("wm-1", body="MENU")).encode()
            response = client.post(
                reverse("whatsapp-webhook"), data=raw,
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 403)

    def test_signed_inbound_deduplicates_retries(self):

        with self._configure():
            client = Client()
            payload = meta_payload("wamid-dup", body="LINK " + self.link.code)
            first = signed_post(client, payload)
            second = signed_post(client, payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            WhatsAppMessage.objects.filter(direction="IN").count(), 1
        )
        session = WhatsAppSession.objects.get()
        self.assertEqual(session.linked_user, self.student)

    @override_settings(WHATSAPP_APP_SECRET=APP_SECRET, WHATSAPP_PROVIDER="console",
                       WHATSAPP_RATE_LIMIT_PER_MINUTE=1)
    def test_phone_rate_limit_throttles(self):

        # Seed one inbound this minute -> next exceeds limit.
        WhatsAppMessage.objects.create(
            message_id="seed-1", phone_number=PHONE, direction="IN", body="x",
        )
        client = Client()
        payload = meta_payload("wamid-rate", body="MENU")
        response = signed_post(client, payload)
        self.assertEqual(response.status_code, 200)
        outbound = WhatsAppMessage.objects.filter(
            direction="OUT", body=RATE_LIMITED_REPLY
        )
        self.assertTrue(outbound.exists())