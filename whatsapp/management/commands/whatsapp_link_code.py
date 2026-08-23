"""Generate a WhatsApp link code for a user (printed to stdout; never in logs)."""

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from whatsapp.services import create_link_code


class Command(BaseCommand):
    help = "Create a WhatsApp phone-linking code for a user."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        user = User.objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"No user '{options['username']}'.")
        link = create_link_code(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Code for {user.username}: {link.code} "
                f"(expires {link.expires_at:%Y-%m-%d %H:%M})"
            )
        )