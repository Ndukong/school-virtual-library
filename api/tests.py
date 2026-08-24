"""JSON API v1 tests (WP11): permission filtering, ownership, role filters."""

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from documents.models import DocumentChunk
from library.models import Resource
from question_bank.models import Question
from question_bank.services import approve_question
from schools.models import School
from subjects.models import Subject

PASSWORD = "ComplexPass123!"


class ApiTestBase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")
        self.physics = Subject.objects.create(school=self.school_a, name="Physics")
        self.teacher_a = User.objects.create_user(
            "apicha", password=PASSWORD, role=User.Role.TEACHER, school=self.school_a
        )
        self.student_a = User.objects.create_user(
            "apisua", password=PASSWORD, role=User.Role.STUDENT, school=self.school_a
        )
        self.student_b = User.objects.create_user(
            "apisub", password=PASSWORD, role=User.Role.STUDENT, school=self.school_b
        )

    def make_resource(self, school=None, title="EM Notes", language="en"):
        school = school or self.school_a
        uploader = self.teacher_a if school == self.school_a else self.student_b
        resource = Resource.objects.create(
            school=school, title=title, uploaded_by=uploader,
            resource_type=Resource.ResourceType.NOTES,
            access_policy=Resource.AccessPolicy.SCHOOL,
            licensing_status=Resource.LicensingStatus.TEACHER_CREATED,
            language=language,
        )
        self.chunk = DocumentChunk.objects.create(
            resource=resource, sequence=1, page_start=1, page_end=1,
            text="Electromagnetic induction uses a coil and a changing magnetic field.",
        )
        return resource

    def make_question(self, school=None, approved=True, pending=False, language="en", topic="Induction"):
        school = school or self.school_a
        question = Question.objects.create(
            school=school,
            subject=self.physics if school == self.school_a else None,
            topic=topic, body=f"Body about {topic}.",
            correct_answer="Answer.", options=["Answer.", "Wrong.", "Maybe"],
            marks=2, question_type=Question.QuestionType.MCQ,
            language=language,
            author=self.teacher_a if school == self.school_a else self.student_b,
            approval_status=(
                Question.ApprovalStatus.PENDING_REVIEW if pending
                else Question.ApprovalStatus.DRAFT
            ),
        )
        if approved:
            approve_question(self.teacher_a, question)
        return question


class ResourceApiTests(ApiTestBase):
    def test_anonymous_gets_json_401(self):
        response = Client().get(reverse("api-resources"))
        self.assertEqual(response.status_code, 401)
        payload = json.loads(response.content)
        self.assertIn("error", payload)

    def test_list_is_permission_filtered_to_own_school(self):
        self.make_resource(school=self.school_a, title="Alpha Doc")
        self.make_resource(school=self.school_b, title="Beta Doc")

        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("api-resources"))
        raw = response.content.decode()
        self.assertIn("Alpha Doc", raw)
        self.assertNotIn("Beta Doc", raw)

    def test_list_language_filter(self):
        self.make_resource(title="English Doc", language="en")
        self.make_resource(title="French Doc", language="fr")

        client = Client()
        client.force_login(self.student_a)
        fr_page = client.get(reverse("api-resources") + "?language=fr")
        raw_fr = fr_page.content.decode()
        self.assertIn("French Doc", raw_fr)
        self.assertNotIn("English Doc", raw_fr)

        en_page = client.get(reverse("api-resources") + "?language=en")
        self.assertIn("English Doc", en_page.content.decode())
        self.assertNotIn("French Doc", en_page.content.decode())

    def test_list_query_filter(self):
        self.make_resource(title="Intro to magnets")
        client = Client()
        client.force_login(self.student_a)
        page = client.get(reverse("api-resources") + "?q=magnets")
        self.assertIn("Intro to magnets", page.content.decode())

    def test_list_pagination_meta(self):
        for index in range(5):
            self.make_resource(title=f"Bulky Doc {index}")
        client = Client()
        client.force_login(self.student_a)
        page = client.get(reverse("api-resources") + "?page_size=2")
        payload = json.loads(page.content)
        self.assertEqual(payload["count"], 5)
        self.assertEqual(len(payload["results"]), 2)
        self.assertTrue(payload["next"])


class SearchApiTests(ApiTestBase):
    def test_search_requires_min_query_length(self):
        client = Client()
        client.force_login(self.student_a)
        self.assertEqual(client.get(reverse("api-search") + "?q=x").status_code, 400)

    def test_search_is_permission_filtered_and_has_snippets(self):
        self.make_resource(school=self.school_a, title="Alpha Doc")
        self.make_resource(school=self.school_b, title="Beta Doc")

        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("api-search") + "?q=electromagnetic+induction")
        payload = json.loads(response.content)
        raw = response.content.decode()
        self.assertIn("Alpha Doc", raw)
        self.assertNotIn("Beta Doc", raw)
        self.assertGreater(payload["count"], 0)


class AskApiTests(ApiTestBase):
    @override_settings(RAG_USE_CACHE=False)
    def test_ask_returns_answer_and_owner_can_fetch_it(self):
        self.make_resource(school=self.school_a)

        client = Client()
        client.force_login(self.student_a)
        response = client.post(
            reverse("api-ask"),
            data=json.dumps({"question": "What is electromagnetic induction?"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn("answer", payload)
        self.assertIn("public_id", payload)

        whoami = client.get(payload["answer_url"])
        self.assertEqual(whoami.status_code, 200)

        foreign = Client()
        foreign.force_login(self.student_b)
        self.assertEqual(foreign.get(payload["answer_url"]).status_code, 404)

    def test_ask_empty_question_is_400(self):
        client = Client()
        client.force_login(self.student_a)
        self.assertEqual(client.post(reverse("api-ask"), data={"question": "  "}).status_code, 400)

    def test_ask_unknown_scope_is_400(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.post(
            reverse("api-ask"), data={"question": "hi?", "scope": "TIME_TRAVEL"}
        )
        self.assertEqual(response.status_code, 400)

    def test_ask_rate_limited(self):
        self.make_resource(school=self.school_a)
        client = Client()
        client.force_login(self.student_a)
        statuses = []
        for _ in range(12):
            statuses.append(
                client.post(reverse("api-ask"), data={"question": "hi there?"}).status_code
            )
        self.assertIn(200, statuses)
        self.assertEqual(statuses[-1], 429)


class QuestionApiTests(ApiTestBase):
    def test_student_sees_only_approved_questions(self):
        approved = self.make_question(approved=True)
        pending = self.make_question(approved=False)
        self.make_question(school=self.school_b, approved=False)

        client = Client()
        client.force_login(self.student_a)
        payload = json.loads(client.get(reverse("api-questions")).content)
        ids = [row["public_id"] for row in payload["results"]]
        self.assertIn(str(approved.public_id), ids)
        self.assertNotIn(str(pending.public_id), ids)
        self.assertEqual(len(ids), 1)

    def test_teacher_sees_pending_review_but_not_other_school(self):
        self.make_question(approved=True)
        self.make_question(pending=True, approved=False)
        self.make_question(school=self.school_b, approved=False)

        client = Client()
        client.force_login(self.teacher_a)
        payload = json.loads(client.get(reverse("api-questions")).content)
        statuses = {row["approval_status"] for row in payload["results"]}
        self.assertEqual(statuses, {"APPROVED", "PENDING_REVIEW"})
        raw = client.get(reverse("api-questions")).content.decode()
        self.assertNotIn("Beta", raw)

    def test_questions_language_filter(self):
        fr = self.make_question(approved=True, language="fr", topic="Electrique")
        self.make_question(approved=True, language="en", topic="Induction")

        client = Client()
        client.force_login(self.student_a)
        payload = json.loads(
            client.get(reverse("api-questions") + "?language=fr").content
        )
        ids = [row["public_id"] for row in payload["results"]]
        self.assertEqual(ids, [str(fr.public_id)])

    def test_anonymous_gets_json_401(self):
        self.assertEqual(Client().get(reverse("api-questions")).status_code, 401)