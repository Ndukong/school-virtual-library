from django.core.exceptions import ValidationError
from django.test import TestCase

from classes.models import SchoolClass
from schools.models import School


class SchoolClassModelTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")

    def test_str_includes_school_and_name(self):
        school_class = SchoolClass.objects.create(school=self.school_a, name="Form 1")
        self.assertIn("Alpha Academy", str(school_class))
        self.assertIn("Form 1", str(school_class))

    def test_class_name_unique_per_school(self):
        SchoolClass.objects.create(school=self.school_a, name="Form 1")
        duplicate = SchoolClass(school=self.school_a, name="Form 1")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_same_class_name_across_schools_allowed(self):
        SchoolClass.objects.create(school=self.school_a, name="Form 1")
        other = SchoolClass.objects.create(school=self.school_b, name="Form 1")
        other.full_clean()