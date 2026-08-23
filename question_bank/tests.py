from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from ai.models import AIGeneration, AIInteraction
from question_bank.models import Question
from question_bank.services import (
    WorkflowError,
    approve_question,
    find_duplicates,
    import_from_ai_generation,
    parse_practice_questions,
    questions_for_exam,
    reject_question,
    submit_for_review,
)
from schools.models import School
from subjects.models import Subject

PASSWORD = "ComplexPass123!"


def make_question(**overrides):
    defaults = dict(
        school=overrides.pop("school"),
        topic="Electromagnetism",
        body=overrides.pop("body", "State Faraday's law of electromagnetic induction."),
        correct_answer=overrides.pop("correct_answer",
                                     "The induced EMF is proportional to the rate of change of flux."),
        author=overrides.pop("author"),
    )
    defaults.update(overrides)
    return Question.objects.create(**defaults)


class QuestionBankTestBase(TestCase):
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
        self.admin_a = User.objects.create_user(
            "adma", password=PASSWORD, role=User.Role.ADMIN,
            school=self.school_a, is_staff=True,
        )


class QuestionModelTests(QuestionBankTestBase):
    def test_defaults_and_str(self):
        question = make_question(school=self.school_a, author=self.teacher_a)
        self.assertEqual(question.approval_status, Question.ApprovalStatus.DRAFT)
        self.assertEqual(question.marks, 1)
        self.assertEqual(question.bloom_level, Question.BloomLevel.KNOWLEDGE)
        self.assertIn("Faraday", str(question))

    def test_mcq_requires_two_options(self):
        with self.assertRaises(Exception):
            make_question(
                school=self.school_a, author=self.teacher_a,
                question_type=Question.QuestionType.MCQ,
                options=["Only one"],
            )

    def test_mcq_options_stored(self):
        question = make_question(
            school=self.school_a, author=self.teacher_a,
            question_type=Question.QuestionType.MCQ,
            options=["A. One tesla", "B. One weber", "C. One henry"],
        )
        self.assertEqual(len(question.options), 3)

    def test_true_false_gets_default_options(self):
        question = make_question(
            school=self.school_a, author=self.teacher_a,
            question_type=Question.QuestionType.TRUE_FALSE,
            options=None,
        )
        self.assertEqual(question.options, ["True", "False"])

    def test_non_mcq_clears_options(self):
        question = make_question(
            school=self.school_a, author=self.teacher_a,
            options=["stray"],
        )
        self.assertIsNone(question.options)

    def test_marks_bounds(self):
        with self.assertRaises(Exception):
            make_question(school=self.school_a, author=self.teacher_a, marks=0)
        with self.assertRaises(Exception):
            make_question(school=self.school_a, author=self.teacher_a, marks=500)

    def test_subject_from_other_school_rejected(self):
        foreign_subject = Subject.objects.create(school=self.school_b, name="Physics")
        with self.assertRaises(Exception):
            make_question(
                school=self.school_a, author=self.teacher_a, subject=foreign_subject,
            )

    def test_editing_content_resets_approval(self):
        question = make_question(school=self.school_a, author=self.teacher_a)
        approve_question(self.admin_a, question)
        self.assertEqual(question.approval_status, Question.ApprovalStatus.APPROVED)

        question.body = "Revised: define magnetic flux density."
        question.save()
        question.refresh_from_db()
        self.assertEqual(question.approval_status, Question.ApprovalStatus.DRAFT)
        self.assertIsNone(question.approved_by)
        self.assertIsNone(question.approved_at)


class WorkflowTests(QuestionBankTestBase):
    def setUp(self):
        super().setUp()
        self.question = make_question(school=self.school_a, author=self.teacher_a)

    def test_full_lifecycle(self):
        submit_for_review(self.teacher_a, self.question)
        self.question.refresh_from_db()
        self.assertEqual(self.question.approval_status, Question.ApprovalStatus.PENDING_REVIEW)

        approve_question(self.admin_a, self.question)
        self.question.refresh_from_db()
        self.assertEqual(self.question.approval_status, Question.ApprovalStatus.APPROVED)
        self.assertEqual(self.question.approved_by, self.admin_a)
        self.assertIsNotNone(self.question.approved_at)

    def test_reject_records_notes(self):
        reject_question(self.admin_a, self.question, "Ambiguous wording.")
        self.question.refresh_from_db()
        self.assertEqual(self.question.approval_status, Question.ApprovalStatus.REJECTED)
        self.assertIn("Ambiguous", self.question.review_notes)

    def test_rejected_cannot_be_approved_directly(self):
        reject_question(self.admin_a, self.question)
        with self.assertRaises(WorkflowError):
            approve_question(self.admin_a, self.question)

    def test_double_submit_raises(self):
        submit_for_review(self.teacher_a, self.question)
        with self.assertRaises(WorkflowError):
            submit_for_review(self.teacher_a, self.question)

    def test_cross_school_teacher_cannot_manage(self):
        with self.assertRaises(WorkflowError):
            approve_question(self.teacher_b, self.question)

    def test_student_role_cannot_manage(self):
        with self.assertRaises(WorkflowError):
            approve_question(self.student_a, self.question)


class ExamQuerysetTests(QuestionBankTestBase):
    def test_only_approved_active_same_school(self):
        approved = make_question(
            school=self.school_a, author=self.teacher_a, topic="Induction",
            subject=self.physics_a,
        )
        approve_question(self.admin_a, approved)

        make_question(school=self.school_a, author=self.teacher_a,
                      subject=self.physics_a)          # DRAFT
        pending = make_question(school=self.school_a, author=self.teacher_a,
                                subject=self.physics_a)
        submit_for_review(self.teacher_a, pending)                          # PENDING
        rejected = make_question(school=self.school_a, author=self.teacher_a)
        reject_question(self.admin_a, rejected)                             # REJECTED
        physics_b = Subject.objects.create(school=self.school_b, name="Physics")
        foreign = make_question(school=self.school_b, author=self.teacher_b,
                                subject=physics_b)
        approve_question(self.teacher_b, foreign)                           # other school

        queryset = questions_for_exam(self.school_a, subject=self.physics_a)
        self.assertEqual(list(queryset), [approved])

    def test_filters_narrow_results(self):
        q1 = make_question(
            school=self.school_a, author=self.teacher_a,
            topic="Induction", difficulty=Question.Difficulty.HARD,
            bloom_level=Question.BloomLevel.ANALYSIS,
            question_type=Question.QuestionType.STRUCTURED,
            subject=self.physics_a,
        )
        approve_question(self.admin_a, q1)
        easy = make_question(
            school=self.school_a, author=self.teacher_a,
            topic="Kinematics", difficulty=Question.Difficulty.EASY,
            subject=self.physics_a,
        )
        approve_question(self.admin_a, easy)

        self.assertEqual(questions_for_exam(self.school_a, topic="induction").count(), 1)
        self.assertEqual(
            questions_for_exam(self.school_a, difficulty=Question.Difficulty.HARD).count(), 1
        )
        self.assertEqual(
            questions_for_exam(
                self.school_a, bloom_level=Question.BloomLevel.ANALYSIS
            ).count(),
            1,
        )
        self.assertEqual(questions_for_exam(self.school_a).count(), 2)


class DuplicateDetectionTests(QuestionBankTestBase):
    def test_exact_normalized_duplicate_found(self):
        first = make_question(
            school=self.school_a, author=self.teacher_a,
            body="Define   electromagnetic  induction.",
        )
        second = make_question(
            school=self.school_a, author=self.teacher_a,
            body="define electromagnetic induction",
        )
        duplicates = find_duplicates(second, exclude_pk=second.pk)
        self.assertIn(first.pk, [q.pk for q in duplicates])

    def test_cross_school_not_matched(self):
        make_question(school=self.school_b, author=self.teacher_b,
                      body="State Faraday's law of electromagnetic induction.")
        mine = make_question(school=self.school_a, author=self.teacher_a)
        self.assertEqual(find_duplicates(mine, exclude_pk=mine.pk), [])


class AiImportTests(QuestionBankTestBase):
    def _generation(self, content, user=None):
        user = user or self.teacher_a
        return AIGeneration.objects.create(
            user=user, kind=AIGeneration.Kind.PRACTICE_QUESTIONS,
            scope=AIInteraction.Scope.BOOK, topic="Electromagnetic induction",
            content=content,
        )

    def test_parser_extracts_wellformed_pairs(self):
        text = (
            "Here are practice questions:\n"
            "Q: State Lenz's law.\nA: The induced current opposes the change causing it.\n\n"
            "Q: What does a step-down transformer change?\nA: Voltage decreases; current increases.\n\n"
            "Random heading without pair."
        )
        items, skipped = parse_practice_questions(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(skipped, 0)
        self.assertIn("Lenz", items[0][0])

    def test_parser_counts_malformed_blocks(self):
        items, skipped = parse_practice_questions("Q: No answer here.\nQ2 noise")
        self.assertEqual(items, [])
        self.assertEqual(skipped, 1)

    def test_import_creates_pending_questions_with_traceability(self):
        generation = self._generation(
            "Q: First question?\nA: First answer.\n\n"
            "Q: Second question?\nA: Second answer.\n\n"
            "Q: Orphan without answer.\n"
        )
        stats = import_from_ai_generation(self.teacher_a, generation)
        self.assertEqual(stats["imported"], 2)
        self.assertEqual(stats["skipped"], 1)
        questions = Question.objects.filter(ai_generation=generation)
        self.assertEqual(questions.count(), 2)
        for question in questions:
            self.assertEqual(question.approval_status, Question.ApprovalStatus.PENDING_REVIEW)
            self.assertEqual(question.author, self.teacher_a)
            self.assertEqual(question.topic, "Electromagnetic induction")

    def test_import_rejects_non_practice_kind(self):
        generation = AIGeneration.objects.create(
            user=self.teacher_a, kind=AIGeneration.Kind.SUMMARY,
            scope=AIInteraction.Scope.LIBRARY, content="Summary text.",
        )
        with self.assertRaises(ValueError):
            import_from_ai_generation(self.teacher_a, generation)

    def test_cannot_import_someone_elses_generation(self):
        generation = self._generation("Q: X?\nA: Y.", user=self.teacher_b)
        with self.assertRaises(WorkflowError):
            import_from_ai_generation(self.teacher_a, generation)


class QuestionViewTests(QuestionBankTestBase):
    def setUp(self):
        super().setUp()
        self.question = make_question(school=self.school_a, author=self.teacher_a)

    def test_anonymous_redirected(self):
        response = Client().get(reverse("question-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_student_forbidden_on_list_and_detail(self):
        client = Client()
        client.force_login(self.student_a)
        self.assertEqual(client.get(reverse("question-list")).status_code, 403)
        detail = reverse("question-detail", args=[self.question.public_id])
        self.assertEqual(client.get(detail).status_code, 403)

    def test_teacher_sees_list_and_detail(self):
        client = Client()
        client.force_login(self.teacher_a)
        self.assertContains(client.get(reverse("question-list")), "Faraday")
        detail = reverse("question-detail", args=[self.question.public_id])
        response = client.get(detail)
        self.assertContains(response, "Answer")
        self.assertContains(response, "rate of change of flux")

    def test_cross_school_detail_hidden(self):
        client = Client()
        client.force_login(self.teacher_b)
        detail = reverse("question-detail", args=[self.question.public_id])
        self.assertEqual(client.get(detail).status_code, 404)

    def test_create_then_workflow_via_actions(self):
        client = Client()
        client.force_login(self.teacher_a)
        payload = {
            "topic": "Kinematics",
            "body": "Define acceleration.",
            "correct_answer": "Rate of change of velocity.",
            "marks": 2,
            "question_type": Question.QuestionType.SHORT_STRUCTURED,
            "bloom_level": Question.BloomLevel.KNOWLEDGE,
            "difficulty": Question.Difficulty.EASY,
        }
        response = client.post(reverse("question-create"), payload)
        question = Question.objects.get(body__icontains="acceleration")
        self.assertRedirects(response, reverse("question-detail", args=[question.public_id]))
        self.assertEqual(question.approval_status, Question.ApprovalStatus.DRAFT)

        client.post(reverse("question-action", args=[question.public_id, "submit"]))
        client.post(reverse("question-action", args=[question.public_id, "approve"]))
        question.refresh_from_db()
        self.assertEqual(question.approval_status, Question.ApprovalStatus.APPROVED)

    def test_student_cannot_approve_via_post(self):
        client = Client()
        client.force_login(self.student_a)
        response = client.post(reverse("question-action", args=[self.question.public_id, "approve"]))
        self.assertEqual(response.status_code, 403)
        self.question.refresh_from_db()
        self.assertEqual(self.question.approval_status, Question.ApprovalStatus.DRAFT)

    def test_import_run_view_redirects_to_pending(self):
        generation = AIGeneration.objects.create(
            user=self.teacher_a, kind=AIGeneration.Kind.PRACTICE_QUESTIONS,
            scope=AIInteraction.Scope.LIBRARY, topic="Induction",
            content="Q: One?\nA: One answer.",
        )
        client = Client()
        client.force_login(self.teacher_a)
        response = client.post(
            reverse("question-import-run"), {"generation": str(generation.public_id)}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=PENDING_REVIEW", response.url)
        self.assertEqual(Question.objects.filter(topic="Induction").count(), 1)