from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from examinations.models import Exam, ExamQuestion
from learning.models import AttemptResponse, PracticeAttempt
from learning.services import (
    PracticeError,
    get_owned_attempt,
    progress_summary,
    recommend_topics,
    record_self_mark,
    start_from_exam,
    start_quiz,
    submit_attempt,
)
from question_bank.models import Question
from question_bank.services import approve_question
from schools.models import School
from subjects.models import Subject

PASSWORD = "ComplexPass123!"


class PracticeTestBase(TestCase):
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
        self.student_b = User.objects.create_user(
            "stub", password=PASSWORD, role=User.Role.STUDENT, school=self.school_b
        )

    def make_question(self, marks=2, topic="Induction",
                      qtype=Question.QuestionType.SHORT_STRUCTURED,
                      options=None, correct="The induced EMF opposes the change.",
                      school=None, approved=True):
        question = Question.objects.create(
            school=school or self.school_a,
            subject=self.physics_a if (school or self.school_a) == self.school_a else None,
            topic=topic,
            body=f"Question about {topic} ({qtype}, {marks} marks).",
            correct_answer=correct,
            options=options,
            question_type=qtype,
            marks=marks,
            author=self.teacher_a if (school or self.school_a) == self.school_a else self.teacher_b,
        )
        if approved:
            approve_question(
                self.admin_a if (school or self.school_a) == self.school_a else self.teacher_b,
                question,
            )
        return question

    def make_mcq(self, marks=2, topic="Induction", correct="B. One weber", school=None):
        return self.make_question(
            marks=marks, topic=topic, school=school,
            qtype=Question.QuestionType.MCQ,
            options=["A. One tesla", correct, "C. One henry", "D. One volt"],
            correct=correct,
        )

    def make_tf(self, marks=1, topic="Induction", correct="True", school=None):
        return self.make_question(
            marks=marks, topic=topic, school=school,
            qtype=Question.QuestionType.TRUE_FALSE,
            options=None,
            correct=correct,
        )


class QuizCreationTests(PracticeTestBase):
    def test_draws_approved_school_questions_only(self):
        mine = self.make_mcq()
        self.make_question(school=self.school_b)  # other school, approved? no author there
        draft = self.make_question()
        draft.approval_status = Question.ApprovalStatus.DRAFT
        draft.save()

        attempt = start_quiz(self.student_a, size=10)
        pks = [r.question.pk for r in attempt.responses.all()]
        self.assertIn(mine.pk, pks)
        self.assertNotIn(draft.pk, pks)
        for response in attempt.responses.all():
            self.assertEqual(response.question.school_id, self.school_a.pk)
        self.assertEqual(attempt.status, PracticeAttempt.Status.IN_PROGRESS)
        self.assertEqual(attempt.possible_marks,
                         sum(r.question.marks for r in attempt.responses.all()))

    def test_topic_filter_narrows(self):
        self.make_mcq(topic="Kinematics")
        induction = self.make_mcq(topic="Induction")
        attempt = start_quiz(self.student_a, topic="induction", size=5)
        for response in attempt.responses.all():
            self.assertEqual(response.question.topic, "Induction")
        self.assertIn(induction, [r.question for r in attempt.responses.all()])

    def test_no_questions_is_honest_error(self):
        with self.assertRaises(PracticeError):
            start_quiz(self.student_a)

    def test_size_capped(self):
        for _ in range(4):
            self.make_mcq()
        attempt = start_quiz(self.student_a, size=99)
        self.assertEqual(attempt.responses.count(), 4)  # pool exhausted below cap


class GradingTests(PracticeTestBase):
    def _attempt_with(self, *questions):
        attempt = PracticeAttempt.objects.create(
            student=self.student_a, school=self.school_a,
            possible_marks=sum(q.marks for q in questions),
        )
        for position, question in enumerate(questions, start=1):
            AttemptResponse.objects.create(
                attempt=attempt, question=question, position=position,
            )
        return attempt

    def test_objective_auto_grading(self):
        mcq = self.make_mcq(correct="B. One weber")
        tf = self.make_tf(correct="True")
        attempt = self._attempt_with(mcq, tf)

        answers = {}
        for response in attempt.responses.all():
            if response.question.question_type == Question.QuestionType.MCQ:
                answers[str(response.pk)] = "b. one  weber"  # sloppy but correct
            else:
                answers[str(response.pk)] = "False"  # wrong
        submit_attempt(attempt, answers)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PracticeAttempt.Status.SUBMITTED)
        self.assertEqual(attempt.earned_marks, 2)  # MCQ right, TF wrong
        self.assertEqual(attempt.score_percent, 66.7)
        for response in attempt.responses.all():
            self.assertIsNotNone(response.is_correct)

    def test_structured_awaits_self_marking(self):
        structured = self.make_question(marks=3)
        attempt = self._attempt_with(structured)
        response = attempt.responses.get()
        submit_attempt(attempt, {str(response.pk): "My attempt."})
        response.refresh_from_db()
        self.assertIsNone(response.is_correct)
        self.assertEqual(attempt.earned_marks, 0)

        record_self_mark(self.student_a, response, is_correct=True)
        attempt.refresh_from_db()
        response.refresh_from_db()
        self.assertTrue(response.self_marked)
        self.assertEqual(attempt.earned_marks, 3)
        self.assertEqual(attempt.possible_marks, 3)

    def test_double_submit_blocked(self):
        structured = self.make_question()
        attempt = self._attempt_with(structured)
        response = attempt.responses.get()
        submit_attempt(attempt, {str(response.pk): "Answer."})
        with self.assertRaises(PracticeError):
            submit_attempt(attempt, {str(response.pk): "Again."})

    def test_self_mark_rules(self):
        mcq = self.make_mcq()
        structured = self.make_question(marks=2)
        attempt = self._attempt_with(mcq, structured)
        mcq_response = attempt.responses.get(question=mcq)
        structured_response = attempt.responses.get(question=structured)
        submit_attempt(attempt, {})

        with self.assertRaises(PracticeError):
            record_self_mark(self.student_a, mcq_response, True)  # objective
        with self.assertRaises(PracticeError):
            record_self_mark(self.student_a, structured_response, True)
            record_self_mark(self.student_a, structured_response, False)  # double

    def test_cross_student_self_mark_denied(self):
        structured = self.make_question()
        attempt = self._attempt_with(structured)
        response = attempt.responses.get()
        submit_attempt(attempt, {str(response.pk): "Answer."})
        with self.assertRaises(Exception):
            record_self_mark(self.student_b, response, True)


class ExamPracticeTests(PracticeTestBase):
    def test_published_exam_practice_flow(self):
        q1 = self.make_question(marks=5)
        q2 = self.make_mcq(marks=5)
        exam = Exam.objects.create(
            title="Physics Midterm", school=self.school_a, subject=self.physics_a,
            duration_minutes=60, total_marks=10, created_by=self.teacher_a,
            status=Exam.Status.PUBLISHED,
        )
        ExamQuestion.objects.create(exam=exam, question=q1, position=1, marks=5)
        ExamQuestion.objects.create(exam=exam, question=q2, position=2, marks=5)

        attempt = start_from_exam(self.student_a, exam)
        self.assertEqual(attempt.source_type, PracticeAttempt.Source.PUBLISHED_EXAM)
        self.assertEqual([r.position for r in attempt.responses.order_by("position")], [1, 2])
        self.assertEqual(attempt.possible_marks, 10)

    def test_draft_exam_rejected(self):
        exam = Exam.objects.create(
            title="Draft exam", school=self.school_a, subject=self.physics_a,
            duration_minutes=60, total_marks=10, created_by=self.teacher_a,
            status=Exam.Status.DRAFT,
        )
        with self.assertRaises(PracticeError):
            start_from_exam(self.student_a, exam)

    def test_cross_school_exam_rejected(self):
        physics_b = Subject.objects.create(school=self.school_b, name="Physics")
        exam = Exam.objects.create(
            title="Beta exam", school=self.school_b, subject=physics_b,
            duration_minutes=60, total_marks=10,
            created_by=self.teacher_b,
            status=Exam.Status.PUBLISHED,
        )
        with self.assertRaises(PracticeError):
            start_from_exam(self.student_a, exam)


class PrivacyTests(PracticeTestBase):
    def test_ownership_enforced(self):
        attempt = PracticeAttempt.objects.create(
            student=self.student_a, school=self.school_a,
        )
        with self.assertRaises(Exception):
            get_owned_attempt(self.student_b, attempt.public_id)

    def test_progress_is_private(self):
        mine = self.make_question()
        attempt = PracticeAttempt.objects.create(
            student=self.student_a, school=self.school_a, possible_marks=2,
        )
        response = AttemptResponse.objects.create(attempt=attempt, question=mine, position=1)
        submit_attempt(attempt, {str(response.pk): "Something."})

        summary_a = progress_summary(self.student_a)
        summary_b = progress_summary(self.student_b)
        self.assertEqual(summary_a["submitted_count"], 1)
        self.assertEqual(summary_b["submitted_count"], 0)


class RecommendationTests(PracticeTestBase):
    def test_weakest_topics_first(self):
        weak = self.make_question(topic="Optics", marks=1)
        strong = self.make_question(topic="Kinematics", marks=1)
        attempt = PracticeAttempt.objects.create(
            student=self.student_a, school=self.school_a, possible_marks=2,
        )
        r1 = AttemptResponse.objects.create(attempt=attempt, question=weak, position=1)
        r2 = AttemptResponse.objects.create(attempt=attempt, question=strong, position=2)
        submit_attempt(attempt, {str(r1.pk): "x", str(r2.pk): "y"})
        record_self_mark(self.student_a, r1, is_correct=False)
        record_self_mark(self.student_a, r2, is_correct=True)

        recommendations = recommend_topics(self.student_a)
        self.assertEqual(recommendations[0]["topic"], "Optics")
        self.assertEqual(recommendations[0]["accuracy"], 0.0)
        self.assertEqual(recommendations[1]["topic"], "Kinematics")


class PracticeViewTests(PracticeTestBase):
    def test_anonymous_redirected(self):
        response = Client().get(reverse("practice-home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_teacher_forbidden_on_student_area(self):
        client = Client()
        client.force_login(self.teacher_a)
        self.assertEqual(client.get(reverse("practice-home")).status_code, 403)
        self.assertEqual(client.get(reverse("practice-progress")).status_code, 403)

    def test_attempt_page_hides_answers_before_submit(self):
        self.make_mcq(correct="B. One weber")
        self.make_question(marks=3, topic="Kinematics")  # excluded by filter
        attempt = start_quiz(self.student_a, topic="Induction", size=1)
        client = Client()
        client.force_login(self.student_a)
        response = client.get(reverse("attempt-page", args=[attempt.public_id]))
        self.assertContains(response, "One weber")  # options shown
        self.assertNotContains(response, "Correct answer")
        self.assertNotContains(response, "Marking scheme")

    def test_result_page_shows_explanations_after_submit(self):
        mcq = self.make_mcq(correct="B. One weber")
        attempt = PracticeAttempt.objects.create(
            student=self.student_a, school=self.school_a, possible_marks=2,
        )
        response = AttemptResponse.objects.create(attempt=attempt, question=mcq, position=1)
        submit_attempt(attempt, {str(response.pk): "B. One weber"})
        client = Client()
        client.force_login(self.student_a)
        result = client.get(reverse("attempt-result", args=[attempt.public_id]))
        self.assertContains(result, "Correct answer")
        self.assertContains(result, "One weber")

    def test_cross_student_result_404(self):
        mcq = self.make_mcq()
        attempt = PracticeAttempt.objects.create(
            student=self.student_a, school=self.school_a, possible_marks=2,
        )
        AttemptResponse.objects.create(attempt=attempt, question=mcq, position=1)
        client = Client()
        client.force_login(self.student_b)
        self.assertEqual(
            client.get(reverse("attempt-result", args=[attempt.public_id])).status_code,
            404,
        )

    def test_full_flow_via_views(self):
        self.make_mcq(correct="B. One weber")
        client = Client()
        client.force_login(self.student_a)

        start = client.post(reverse("practice-start"), {"size": "5", "topic": ""})
        attempt = PracticeAttempt.objects.filter(student=self.student_a).latest("pk")
        self.assertRedirects(start, reverse("attempt-page", args=[attempt.public_id]))

        response = attempt.responses.get()
        submitted = client.post(
            reverse("attempt-submit", args=[attempt.public_id]),
            {f"answer_{response.pk}": "B. One weber"},
        )
        attempt.refresh_from_db()
        self.assertRedirects(submitted, reverse("attempt-result", args=[attempt.public_id]))
        self.assertEqual(attempt.earned_marks, attempt.possible_marks)

        progress = client.get(reverse("practice-progress"))
        self.assertContains(progress, "Submitted quizzes")