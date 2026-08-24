"""WhatsApp queue worker (WP6): drains PENDING inbound tasks outside the
webhook so the web request stays sub-second."""

import time

from django.core.management.base import BaseCommand

from whatsapp.services import drain_whatsapp_queue


class Command(BaseCommand):
    help = "Process queued WhatsApp inbound messages (worker)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop", action="store_true", help="Poll forever (daemon mode)."
        )
        parser.add_argument("--interval", type=int, default=3, help="Poll seconds in --loop.")
        parser.add_argument(
            "--limit", type=int, default=50, help="Max tasks drained per pass."
        )

    def handle(self, *args, **options):
        if options["loop"]:
            self.stdout.write(self.style.SUCCESS("WhatsApp worker started; Ctrl+C to stop."))
            while True:
                count = drain_whatsapp_queue(options["limit"])
                if count:
                    self.stdout.write(self.style.SUCCESS(f"Processed {count} task(s)."))
                time.sleep(options["interval"])
        else:
            count = drain_whatsapp_queue(options["limit"])
            self.stdout.write(self.style.SUCCESS(f"Processed {count} task(s)."))