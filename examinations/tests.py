from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from examinations.models import Exam, ExamQuestion
from examinations.services import (
    ExamError,
    assemble_exam,
    mark_ready_for_review,
    publish_exam,
    select_questions,
    suggest_fill_from_ai,
    validate_exam,
)
from question_bank.models import Question
from question_bank.services import approve_question
from schools.models import School
from subjects.models import Subject

PASSWORD = "ComplexPass123!"


class ExamTestBase(TestCase):
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

    def make_approved(self, marks, topic="Induction",
                      difficulty=Question.Difficulty.MEDIUM,
                      bloom=Question.BloomLevel.KNOWLEDGE,
                      qtype=Question.QuestionType.SHORT_STRUCTURED,
                      body=None, school=None):
        school = school or self.school_a
        question = Question.objects.create(
            school=school,
            subject=self.physics_a if school == self.school_a else None,
            topic=topic,
            body=body or f"Explain a {marks}-mark point about {topic} #{marks}-{len(topic)}.",
            correct_answer="Model answer.",
            marks=marks,
            difficulty=difficulty,
            bloom_level=bloom,
            question_type=qtype,
            author=self.teacher_a if school == self.school_a else self.teacher_b,
        )
        approve_question(self.admin_a if school == self.school_a else self.teacher_b, question)
        return question

    def make_exam(self, total_marks=40, topics=("induction",), **overrides):
        defaults = dict(
            title="End of term Physics",
            school=self.school_a,
            subject=self.physics_a,
            duration_minutes=90,
            total_marks=total_marks,
            created_by=self.teacher_a,
            config={
                "topics": list(topics),
                "question_types": [],
                "bloom_distribution": overrides.pop("bloom_distribution", {}),
            },
        )
        defaults.update(overrides)
        return Exam.objects.create(**defaults)


class SelectionTests(ExamTestBase):
    def test_exact_total_from_skills_example(self):
        # SKILLS.md section 11: 5 + 5 + 10 + 20 must equal 40.
        for marks in (5, 5, 10, 20):
            self.make_approved(marks)
        picked = select_questions(
            school=self.school_a, subject=self.physics_a,
            topics=["induction"], total_marks=40,
        )
        self.assertEqual(sum(q.marks for q in picked), 40)

    def test_shortfall_reported_honestly(self):
        self.make_approved(5)
        with self.assertRaises(ExamError) as ctx:
            select_questions(school=self.school_a, total_marks=40)
        self.assertIn("5 of 40", str(ctx.exception))

    def test_selection_prefers_requested_topics_then_larger_marks(self):
        relevant = self.make_approved(10, topic="Induction")
        irrelevant_big = self.make_approved(30, topic="Kinematics")
        picked = select_questions(
            school=self.school_a, topics=["induction"], total_marks=10,
        )
        self.assertIn(relevant, picked)
        self.assertNotIn(irrelevant_big, picked)

    def test_type_filter_respected(self):
        essay = self.make_approved(40, qtype=Question.QuestionType.ESSAY)
        structured = self.make_approved(10, qtype=Question.QuestionType.STRUCTURED)
        picked = select_questions(
            school=self.school_a,
            question_types=[Question.QuestionType.ESSAY.value],
            total_marks=40,
        )
        self.assertIn(essay, picked)
        self.assertNotIn(structured, picked)

    def test_unapproved_and_foreign_excluded(self):
        draft = Question.objects.create(
            school=self.school_a, subject=self.physics_a, topic="Induction",
            body="Draft question.", correct_answer="A.", marks=40,
            author=self.teacher_a,
        )  # never approved
        foreign = self.make_approved(40, school=self.school_b)
        with self.assertRaises(ExamError):
            select_questions(school=self.school_a, total_marks=40)


class ValidationTests(ExamTestBase):
    def _assemble(self, total=40):
        exam = self.make_exam(total_marks=total)
        assemble_exam(exam)
        return exam

    def test_assembled_exam_validates_clean(self):
        for marks in (5, 10, 25):
            self.make_approved(marks)
        exam = self._assemble(40)
        report = validate_exam(exam)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.achieved_marks, 40)
        self.assertTrue(report.topic_coverage.get("induction"))

    def test_missing_topic_flagged(self):
        self.make_approved(40, topic="Optics")
        exam = self.make_exam(total_marks=40, topics=("optics", "electromagnetism"))
        assemble_exam(exam)
        report = validate_exam(exam)
        self.assertFalse(report.ok)
        self.assertFalse(report.topic_coverage.get("electromagnetism"))
        self.assertTrue(any("electromagnetism" in e for e in report.errors))

    def test_tampered_marks_break_arithmetic_check(self):
        self.make_approved(15)
        self.make_approved(25)
        exam = self._assemble(40)
        slot = exam.exam_questions.order_by("position").first()
        slot.marks = 99
        slot.save()
        report = validate_exam(exam)
        self.assertFalse(report.ok)
        self.assertIn("114", " ".join(report.errors))
        self.assertIn("requires 40", " ".join(report.errors))

    def test_unapproved_slot_detected(self):
        approved = self.make_approved(40)
        exam = self._assemble(40)
        approved.approval_status = Question.ApprovalStatus.DRAFT
        approved.save(update_fields=["approval_status"])
        report = validate_exam(exam)
        self.assertFalse(report.ok)
        self.assertTrue(any("not approved" in e for e in report.errors))

    def test_bloom_report_actual_vs_requested(self):
        self.make_approved(20, bloom=Question.BloomLevel.KNOWLEDGE)
        self.make_approved(20, bloom=Question.BloomLevel.APPLICATION)
        exam = self.make_exam(
            total_marks=40,
            bloom_distribution={"KNOWLEDGE": 80},
        )
        assemble_exam(exam)
        report = validate_exam(exam)
        knowledge = report.bloom_report["Knowledge"]
        application = report.bloom_report["Application"]
        self.assertEqual(knowledge["actual_pct"], 50.0)
        self.assertGreater(knowledge.get("warning", ""), "")
        self.assertEqual(application["actual_pct"], 50.0)


class WorkflowTests(ExamTestBase):
    def test_publish_requires_ready_state(self):
        self.make_approved(40)
        exam = self.make_exam(total_marks=40)
        with self.assertRaises(ExamError):
            publish_exam(self.teacher_a, exam)

    def test_ready_requires_passing_validation(self):
        exam = self.make_exam(total_marks=40)  # no questions at all
        with self.assertRaises(ExamError):
            mark_ready_for_review(self.teacher_a, exam)
        exam.refresh_from_db()
        self.assertEqual(exam.status, Exam.Status.DRAFT)

    def test_full_flow_to_published(self):
        self.make_approved(15)
        self.make_approved(25)
        exam = self.make_exam(total_marks=40)
        assemble_exam(exam)
        mark_ready_for_review(self.teacher_a, exam)
        publish_exam(self.admin_a, exam)
        exam.refresh_from_db()
        self.assertEqual(exam.status, Exam.Status.PUBLISHED)


class SuggestFillTests(ExamTestBase):
    def test_suggest_creates_pending_questions_not_exam_slots(self):
        exam = self.make_exam(total_marks=40)
        partial = self.make_approved(10)
        ExamQuestion.objects.create(exam=exam, question=partial, position=1, marks=10)

        provider = mock.MagicMock()
        result = mock.MagicMock()
        result.text = ("Q: State one use of a transformer.\n"
                       "A: Changing voltage levels in power distribution.\n\n"
                       "Q: Define magnetic flux.\n"
                       "A: Product of field strength and area perpendicular to it.")
        provider.generate.return_value = result
        stats = suggest_fill_from_ai(self.teacher_a, exam, chat_provider=provider)

        self.assertEqual(stats["suggested"], 2)
        pending = Question.objects.filter(approval_status=Question.ApprovalStatus.PENDING_REVIEW)
        self.assertEqual(pending.count(), 2)
        for question in pending:
            self.assertIsNone(question.exam_slots.first())  # exam untouched
        provider.generate.assert_called_once()

    def test_suggest_refuses_when_target_met(self):
        self.make_approved(40)
        exam = self.make_exam(total_marks=40)
        assemble_exam(exam)
        with self.assertRaises(ExamError):
            suggest_fill_from_ai(self.teacher_a, exam, chat_provider=mock.MagicMock())

    def test_insufficient_material_is_honest(self):
        exam = self.make_exam(total_marks=40)
        provider = mock.MagicMock()
        result = mock.MagicMock()
        result.text = "INSUFFICIENT"
        provider.generate.return_value = result
        with self.assertRaises(ExamError) as ctx:
            suggest_fill_from_ai(self.teacher_a, exam, chat_provider=provider)
        self.assertIn("could not find enough material", str(ctx.exception))


class ExamViewTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        self.make_approved(15)
        self.make_approved(25)
        self.exam = self.make_exam(total_marks=40)
        assemble_exam(self.exam)

    def test_anonymous_redirected(self):
        response = Client().get(reverse("exam-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_student_forbidden_everywhere(self):
        client = Client()
        client.force_login(self.student_a)
        detail = reverse("exam-detail", args=[self.exam.public_id])
        print_url = reverse("exam-print", args=[self.exam.public_id])
        self.assertEqual(client.get(reverse("exam-list")).status_code, 403)
        self.assertEqual(client.get(detail).status_code, 403)
        self.assertEqual(client.get(print_url).status_code, 404)

    def test_teacher_sees_detail_with_validation_report(self):
        client = Client()
        client.force_login(self.teacher_a)
        response = client.get(reverse("exam-detail", args=[self.exam.public_id]))
        self.assertContains(response, "All checks passed")

    def test_cross_school_hidden(self):
        other_admin = User.objects.create_user(
            "otheradmin", password=PASSWORD, role=User.Role.ADMIN,
            school=self.school_b, is_staff=True,
        )
        client = Client()
        client.force_login(other_admin)
        response = client.get(reverse("exam-detail", args=[self.exam.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_print_views_render_questions_and_key(self):
        client = Client()
        client.force_login(self.teacher_a)
        paper = client.get(reverse("exam-print", args=[self.exam.public_id]))
        self.assertContains(paper, "Total:")
        key = client.get(reverse("exam-print-answers", args=[self.exam.public_id]))
        self.assertContains(key, "Model answer.")

    def test_create_via_form_assembles(self):
        client = Client()
        client.force_login(self.teacher_a)
        payload = {
            "title": "Midterm",
            "subject": str(self.physics_a.pk),
            "duration_minutes": "60",
            "total_marks": "40",
            "topics": "induction",
            "question_types": [Question.QuestionType.SHORT_STRUCTURED],
            "bloom_distribution": "",
            "instructions": "Answer all questions.",
        }
        response = client.post(reverse("exam-create"), payload)
        exam = Exam.objects.get(title="Midterm")
        self.assertRedirects(response, reverse("exam-detail", args=[exam.public_id]))
        self.assertEqual(exam.status, Exam.Status.DRAFT)
        self.assertGreaterEqual(exam.achieved_marks, 1)