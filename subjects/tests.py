from django.core.exceptions import ValidationError
from django.test import TestCase

from schools.models import School
from subjects.models import Subject


class SubjectModelTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")

    def test_str_with_code(self):
        subject = Subject.objects.create(school=self.school_a, name="Physics", code="PHY")
        self.assertIn("Physics", str(subject))
        self.assertIn("PHY", str(subject))

    def test_str_without_code(self):
        subject = Subject.objects.create(school=self.school_a, name="Art")
        self.assertEqual(str(subject), "Art")

    def test_subject_code_unique_per_school(self):
        Subject.objects.create(school=self.school_a, name="Physics", code="PHY")
        duplicate = Subject(school=self.school_a, name="Physical Science", code="PHY")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_same_code_across_schools_allowed(self):
        Subject.objects.create(school=self.school_a, name="Physics", code="PHY")
        other = Subject.objects.create(school=self.school_b, name="Physics", code="PHY")
        other.full_clean()

    def test_multiple_subjects_without_code_allowed(self):
        Subject.objects.create(school=self.school_a, name="Physics")
        second = Subject.objects.create(school=self.school_a, name="Chemistry")
        second.full_clean()

    def test_subject_name_unique_per_school(self):
        Subject.objects.create(school=self.school_a, name="History")
        duplicate = Subject(school=self.school_a, name="History")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()