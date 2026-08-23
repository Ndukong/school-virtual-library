from django.core.exceptions import ValidationError
from django.test import TestCase

from schools.models import School


class SchoolModelTests(TestCase):
    def test_str_returns_name(self):
        school = School.objects.create(name="Hill High School")
        self.assertEqual(str(school), "Hill High School")

    def test_school_name_unique(self):
        School.objects.create(name="Hill High School")
        duplicate = School(name="Hill High School")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()