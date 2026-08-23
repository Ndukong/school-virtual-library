from django.core.exceptions import ValidationError
from django.test import TestCase

from schools.models import School
from subjects.models import Subject
from teachers.models import Teacher


class TeacherModelTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")
        self.physics_a = Subject.objects.create(school=self.school_a, name="Physics")
        self.physics_b = Subject.objects.create(school=self.school_b, name="Physics")
        self.teacher_user_a = self._make_user("tcha", "TEACHER", self.school_a)

    @staticmethod
    def _make_user(username, role, school):
        from accounts.models import User

        return User.objects.create_user(username=username, password="ComplexPass123!", role=role, school=school)

    def test_str_includes_staff_number_when_present(self):
        teacher = Teacher.objects.create(user=self.teacher_user_a, school=self.school_a, staff_number="S-77")
        self.assertIn("S-77", str(teacher))

    def test_staff_number_unique_per_school(self):
        Teacher.objects.create(user=self.teacher_user_a, school=self.school_a, staff_number="S-1")
        other_user = self._make_user("tchb", "TEACHER", self.school_a)
        duplicate = Teacher(user=other_user, school=self.school_a, staff_number="S-1")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_staff_number_blank_allowed_for_multiple_teachers(self):
        other_user = self._make_user("tchc", "TEACHER", self.school_a)
        Teacher.objects.create(user=self.teacher_user_a, school=self.school_a)
        second = Teacher.objects.create(user=other_user, school=self.school_a)
        second.full_clean()

    def test_save_rejects_non_teacher_role(self):
        student_user = self._make_user("stu", "STUDENT", self.school_a)
        profile = Teacher(user=student_user, school=self.school_a)
        with self.assertRaises(ValidationError):
            profile.save()

    def test_clean_rejects_user_from_other_school(self):
        profile = Teacher(user=self.teacher_user_a, school=self.school_b)
        with self.assertRaises(ValidationError) as ctx:
            profile.full_clean()
        self.assertIn("school", ctx.exception.message_dict)

    def test_subjects_must_belong_to_teacher_school(self):
        teacher = Teacher.objects.create(user=self.teacher_user_a, school=self.school_a)
        teacher.subjects.add(self.physics_b)
        with self.assertRaises(ValidationError) as ctx:
            teacher.full_clean()
        self.assertIn("subjects", ctx.exception.message_dict)

    def test_own_school_subjects_accepted(self):
        teacher = Teacher.objects.create(user=self.teacher_user_a, school=self.school_a)
        teacher.subjects.add(self.physics_a)
        teacher.full_clean()
