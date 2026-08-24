"""Delete AI history older than the retention window (data protection).

By default retention is OFF (AI_RETENTION_DAYS=0) and this command refuses to
delete anything without an explicit --days. Always check --dry-run first.

    python manage.py purge_old_ai_data --days 180 --dry-run
    python manage.py purge_old_ai_data --days 180
"""

from django.core.management.base import BaseCommand, CommandError

from ai.retention import purge_ai_history


class Command(BaseCommand):
    help = "Purge AI interaction/generation history older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retention window in days; overrides AI_RETENTION_DAYS.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        try:
            result = purge_ai_history(days=options["days"], dry_run=options["dry_run"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"cutoff: {result['cutoff'].isoformat()}")
        self.stdout.write(f"interactions: {result['interactions']}")
        self.stdout.write(f"generations: {result['generations']}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run: nothing deleted"))
        else:
            self.stdout.write(self.style.SUCCESS("old AI history purged"))