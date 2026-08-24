"""Admin kill switch for the WhatsApp channel (WP6)."""

from django.core.management.base import BaseCommand

from whatsapp.services import channel_enabled, set_channel_enabled


class Command(BaseCommand):
    help = "Enable or disable the WhatsApp channel (admin kill switch)."

    def add_arguments(self, parser):
        parser.add_argument("action", nargs="?", choices=["status", "on", "off"], default="status")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "status":
            self.stdout.write(self.style.SUCCESS(f"channel enabled: {channel_enabled()}"))
            return
        enabled = action == "on"
        set_channel_enabled(enabled)
        self.stdout.write(self.style.SUCCESS(f"WhatsApp channel set to: {enabled}"))