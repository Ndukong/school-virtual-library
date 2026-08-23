from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from ai.models import AIGeneration, AIInteraction
from classes.models import SchoolClass
from examinations.models import Exam
from learning.models import AttemptResponse, PracticeAttempt
from library.models import Resource, ResourceAccessEvent
from question_bank.models import Question
from question_bank.services import approve_question
from reports.services import (
    ai_stats,
    library_stats,
    popular_topics,
    practice_stats,
    teacher_activity,
)
from schools.models import School
from students.models import Student
from subjects.models import Subject

PASSWORD = "ComplexPass123!"


class ReportTestBase(TestCase):
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

    def make_resource(self, school=None, title="Physics Notes", rtype=Resource.ResourceType.NOTES,
                      status=Resource.ProcessingStatus.READY):
        school = school or self.school_a
        return Resource.objects.create(
            school=school, title=title,
            uploaded_by=self.teacher_a if school == self.school_a else self.teacher_b,
            resource_type=rtype, processing_status=status,
        )

    def make_question(self, topic="Induction", user=None, school=None, approved=True,
                      qtype=Question.QuestionType.MCQ):
        school = school or self.school_a
        question = Question.objects.create(
            school=school,
            subject=self.physics_a if school == self.school_a else None,
            topic=topic, body=f"Body about {topic}.",
            correct_answer="Answer.", options=["Answer.", "Wrong.", "Maybe"],
            marks=2, question_type=qtype,
            author=user or (self.teacher_a if school == self.school_a else self.teacher_b),
        )
        if approved:
            approve_question(self.admin_a if school == self.school_a else self.teacher_b, question)
        return question

    def make_submitted_attempt(self, questions, student=None, marks_map=None):
        student = student or self.student_a
        attempt = PracticeAttempt.objects.create(
            student=student, school=self.school_a,
            subject=self.physics_a,
            possible_marks=sum(q.marks for q in questions),
        )
        for position, q in enumerate(questions, start=1):
            AttemptResponse.objects.create(attempt=attempt, question=q, position=position)
        answers = {}
        for response in attempt.responses.all():
            answers[str(response.pk)] = (
                "Answer." if marks_map is None or response.pk in marks_map else "Wrong."
            )
        from learning.services import submit_attempt

        submit_attempt(attempt, answers)
        return attempt


class LibraryStatsTests(ReportTestBase):
    def test_aggregates_and_access_events_scoped(self):
        self.make_resource(title="Notes doc")
        self.make_resource(title="Paper doc", rtype=Resource.ResourceType.PAST_PAPER,
                           status=Resource.ProcessingStatus.FAILED)
        self.make_resource(school=self.school_b, title="Foreign notes")

        ResourceAccessEvent.objects.create(
            resource=Resource.objects.get(title="Notes doc", school=self.school_a),
            user=self.student_a, kind=ResourceAccessEvent.Kind.DOWNLOAD,
        )
        ResourceAccessEvent.objects.create(
            resource=Resource.objects.filter(school=self.school_b).first(),
            user=self.student_a, kind=ResourceAccessEvent.Kind.READ,
        )

        stats = library_stats(self.school_a)
        self.assertEqual(stats["total_resources"], 2)
        self.assertEqual(stats["processing_ready"], 1)
        self.assertEqual(stats["processing_failed"], 1)
        self.assertEqual(stats["access_total"], 1)  # school B event excluded
        self.assertEqual(stats["access_this_month"], 1)

    def test_download_and_read_views_record_events(self):
        from django.core.files.base import ContentFile

        resource = Resource(
            school=self.school_a, title="Event book", uploaded_by=self.teacher_a,
            resource_type=Resource.ResourceType.NOTES,
        )
        resource.file.save("b.pdf", ContentFile(b"%PDF-1.4"), save=False)
        resource.save()

        client = Client()
        client.force_login(self.student_a)
        client.get(reverse("library-download", args=[resource.public_id]))
        client.get(reverse("library-read", args=[resource.public_id]))
        events = ResourceAccessEvent.objects.filter(resource=resource)
        self.assertEqual(events.filter(kind=ResourceAccessEvent.Kind.DOWNLOAD).count(), 1)
        self.assertEqual(events.filter(kind=ResourceAccessEvent.Kind.READ).count(), 1)


class AIStatsTests(ReportTestBase):
    def test_counts_scoped_to_school(self):
        AIInteraction.objects.create(
            user=self.student_a, school=self.school_a, question="q", answer="a",
            used_provider=False,
        )
        AIInteraction.objects.create(
            user=User.objects.create_user("stub", password=PASSWORD,
                                          role=User.Role.STUDENT, school=self.school_b),
            school=self.school_b, question="q", answer="a",
        )
        AIGeneration.objects.create(
            user=self.student_a, school=self.school_a, kind=AIGeneration.Kind.SUMMARY,
            scope=AIInteraction.Scope.LIBRARY, content="c",
        )

        stats = ai_stats(self.school_a)
        self.assertEqual(stats["interaction_total"], 1)
        self.assertEqual(stats["interaction_failures"], 1)
        self.assertEqual(stats["generation_total"], 1)
        self.assertEqual(stats["generation_failures"], 0)

    def test_model_breakdown(self):
        AIInteraction.objects.create(
            user=self.student_a, school=self.school_a, question="q", answer="a",
            model="llama-3.3-70b-versatile",
        )
        stats = ai_stats(self.school_a)
        self.assertEqual(stats["models_used"][0]["model"], "llama-3.3-70b-versatile")


class PracticeStatsTests(ReportTestBase):
    def test_aggregates_never_contain_student_fields(self):
        q1 = self.make_question()
        q2 = self.make_question(topic="Kinematics")
        self.make_submitted_attempt([q1], marks_map={})
        self.make_submitted_attempt([q2])

        stats = practice_stats(self.school_a)
        self.assertEqual(stats["submitted_count"], 2)
        self.assertGreater(stats["average_percent"], 0.0)
        for row in stats["by_subject"]:
            self.assertNotIn("student", row)
        for row in stats["by_class"]:
            self.assertNotIn("student", row)
        self.assertEqual(stats["by_subject"][0]["subject__name"], "Physics")

    def test_class_grouping_via_student_profile(self):
        school_class = SchoolClass.objects.create(school=self.school_a, name="Form 3")
        Student.objects.create(
            user=self.student_a, school=self.school_a,
            school_class=school_class, admission_number="A-1",
        )
        question = self.make_question()
        self.make_submitted_attempt([question])
        stats = practice_stats(self.school_a)
        self.assertEqual(stats["by_class"][0]["student__student_profile__school_class__name"], "Form 3")


class PopularTopicsTests(ReportTestBase):
    def test_aggregate_accuracy_ordering(self):
        optics = self.make_question(topic="Optics")
        moot = self.make_question(topic="Kinematics")
        # a1 answered everything correctly, a2 everything wrongly.
        self.make_submitted_attempt([optics, moot])
        self.make_submitted_attempt([optics, moot], marks_map={})

        topics = popular_topics(self.school_a)
        by_topic = {t["topic"]: t for t in topics}
        self.assertEqual(by_topic["Optics"]["attempted"], 2)
        self.assertEqual(by_topic["Optics"]["accuracy"], 50.0)
        self.assertEqual(by_topic["Kinematics"]["accuracy"], 50.0)


class TeacherActivityTests(ReportTestBase):
    def test_counts_by_teacher(self):
        self.make_resource()  # teacher_a upload
        self.make_question(user=self.teacher_a)
        exam = Exam.objects.create(
            title="Term test", school=self.school_a, subject=self.physics_a,
            duration_minutes=30, total_marks=2, created_by=self.teacher_a,
            status=Exam.Status.DRAFT,
        )
        rows = teacher_activity(self.school_a)
        mine = next(r for r in rows if r["username"] == self.teacher_a.username)
        self.assertEqual(mine["uploads"], 1)
        self.assertEqual(mine["questions"], 1)
        self.assertEqual(mine["exams"], 1)
        self.assertNotIn(self.teacher_b.username, [r["username"] for r in rows])


class ReportViewTests(ReportTestBase):
    def test_student_forbidden(self):
        client = Client()
        client.force_login(self.student_a)
        for path in ("reports-home", "reports-library", "reports-ai",
                     "reports-practice", "reports-teachers"):
            self.assertEqual(client.get(reverse(path)).status_code, 403, path)

    def test_anonymous_redirected(self):
        self.assertEqual(Client().get(reverse("reports-home")).status_code, 302)

    def test_teacher_sees_own_school_reports(self):
        self.make_resource()
        client = Client()
        client.force_login(self.teacher_a)
        response = client.get(reverse("reports-library"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total resources: 1")

    def test_cross_school_teacher_sees_empty_not_foreign(self):
        self.make_resource()  # school A content
        client = Client()
        client.force_login(self.teacher_b)  # school B
        response = client.get(reverse("reports-library"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Physics Notes")

    def test_admin_sees_reports(self):
        self.make_resource()
        client = Client()
        client.force_login(self.admin_a)
        self.assertEqual(client.get(reverse("reports-home")).status_code, 200)

    def test_superuser_school_select(self):
        superuser = User.objects.create_user("root", password=PASSWORD, is_superuser=True)
        self.make_resource(title="Alpha only book")
        self.make_resource(title="Beta only book", school=self.school_b)
        client = Client()
        client.force_login(superuser)
        response_a = client.get(reverse("reports-library"), {"school": str(self.school_a.pk)})
        self.assertContains(response_a, "Alpha Academy")
        self.assertContains(response_a, "Total resources: 1")
        response_b = client.get(reverse("reports-library"), {"school": str(self.school_b.pk)})
        self.assertContains(response_b, "Beta High")
        self.assertContains(response_b, "Total resources: 1")