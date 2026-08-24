"""WP9: AI history retention - purge command and its boundary conditions."""

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from ai.models import AIGeneration, AIInteraction
from ai.retention import purge_ai_history
from schools.models import School

PASSWORD = "ComplexPass123!"


class RetentionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Retention Academy")
        self.student = User.objects.create_user(
            "sturet", password=PASSWORD, role=User.Role.STUDENT, school=self.school
        )

    def _interaction(self, days_ago=None, text="old question"):
        row = AIInteraction.objects.create(
            user=self.student, school=self.school,
            question=text, answer="old answer", used_provider=True,
        )
        if days_ago is not None:
            AIInteraction.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
        return row

    def _generation(self, days_ago=None):
        row = AIGeneration.objects.create(
            user=self.student, school=self.school,
            kind="SUMMARY", scope="LIBRARY", content="old notes", used_provider=True,
        )
        if days_ago is not None:
            AIGeneration.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
        return row

    def test_purge_removes_only_rows_older_than_the_window(self):
        fresh = self._interaction(days_ago=2)
        old = self._interaction(days_ago=200)
        old_gen = self._generation(days_ago=200)
        fresh_gen = self._generation(days_ago=None)

        result = purge_ai_history(days=180)
        self.assertEqual(result["interactions"], 1)
        self.assertFalse(AIInteraction.objects.filter(pk=old.pk).exists())
        self.assertTrue(AIInteraction.objects.filter(pk=fresh.pk).exists())
        self.assertFalse(AIGeneration.objects.filter(pk=old_gen.pk).exists())
        self.assertTrue(AIGeneration.objects.filter(pk=fresh_gen.pk).exists())

    def test_disabled_retention_refuses_to_delete_without_explicit_days(self):
        self._interaction(days_ago=200)
        with self.assertRaises(ValueError):
            purge_ai_history()
        with self.assertRaises(CommandError):
            call_command("purge_old_ai_data")

    def test_dry_run_reports_but_deletes_nothing(self):
        old = self._interaction(days_ago=200)
        result = purge_ai_history(days=180, dry_run=True)
        self.assertEqual(result["interactions"], 1)
        self.assertTrue(AIInteraction.objects.filter(pk=old.pk).exists())

        out = StringIO()
        call_command("purge_old_ai_data", "--days", "180", "--dry-run", stdout=out)
        self.assertTrue(AIInteraction.objects.filter(pk=old.pk).exists())
        self.assertIn("interactions: 1", out.getvalue())
        self.assertIn("nothing deleted", out.getvalue())

    def test_command_purges_when_explicitly_asked(self):
        old = self._interaction(days_ago=200)
        out = StringIO()
        call_command("purge_old_ai_data", "--days", "180", stdout=out)
        self.assertFalse(AIInteraction.objects.filter(pk=old.pk).exists())
        self.assertIn("interactions: 1", out.getvalue())