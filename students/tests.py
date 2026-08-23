from django.core.exceptions import ValidationError
from django.test import TestCase

from classes.models import SchoolClass
from schools.models import School
from students.models import Student


def make_school(name):
    return School.objects.create(name=name)


def make_user(username, role, school=None):
    from accounts.models import User

    return User.objects.create_user(username=username, password="ComplexPass123!", role=role, school=school)


class StudentModelTests(TestCase):
    def setUp(self):
        self.school_a = make_school("Alpha Academy")
        self.school_b = make_school("Beta High")
        self.class_a1 = SchoolClass.objects.create(school=self.school_a, name="Form 1")
        self.student_user_a = make_user("stua", "STUDENT", self.school_a)
        self.student_user_b = make_user("stub", "STUDENT", self.school_b)

    def test_str_includes_admission_number(self):
        student = Student.objects.create(
            user=self.student_user_a, school=self.school_a, admission_number="A-001"
        )
        self.assertIn("A-001", str(student))

    def test_admission_number_unique_per_school(self):
        Student.objects.create(user=self.student_user_a, school=self.school_a, admission_number="DUP")
        another_in_school_a = make_user("stua2", "STUDENT", self.school_a)
        duplicate = Student(user=another_in_school_a, school=self.school_a, admission_number="DUP")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_same_number_across_schools_allowed(self):
        Student.objects.create(user=self.student_user_a, school=self.school_a, admission_number="SHARED")
        other = Student.objects.create(
            user=self.student_user_b, school=self.school_b, admission_number="SHARED"
        )
        other.full_clean()

    def test_save_rejects_non_student_role(self):
        teacher_user = make_user("tch", "TEACHER", self.school_a)
        profile = Student(user=teacher_user, school=self.school_a, admission_number="T-1")
        with self.assertRaises(ValidationError):
            profile.save()

    def test_clean_rejects_user_from_other_school(self):
        profile = Student(user=self.student_user_b, school=self.school_a, admission_number="X-1")
        with self.assertRaises(ValidationError) as ctx:
            profile.full_clean()
        self.assertIn("school", ctx.exception.message_dict)

    def test_clean_rejects_class_from_other_school(self):
        class_b1 = SchoolClass.objects.create(school=self.school_b, name="Form 1")
        profile = Student(
            user=self.student_user_a,
            school=self.school_a,
            school_class=class_b1,
            admission_number="C-1",
        )
        with self.assertRaises(ValidationError) as ctx:
            profile.full_clean()
        self.assertIn("school_class", ctx.exception.message_dict)

    def test_class_mismatch_caught_without_profile_school(self):
        class_b1 = SchoolClass.objects.create(school=self.school_b, name="Form 9")
        profile = Student(user=self.student_user_a, school_class=class_b1, admission_number="M-1")
        with self.assertRaises(ValidationError):
            profile.full_clean()
