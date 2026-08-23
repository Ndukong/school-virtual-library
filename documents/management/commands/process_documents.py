"""Worker for the database-backed document processing queue."""

import time

from django.core.management.base import BaseCommand

from documents.dispatcher import drain_queue, enqueue
from documents.models import ProcessingJob
from library.models import Resource


class Command(BaseCommand):
    help = (
        "Process pending document jobs. Run alongside the web server "
        "(e.g. in a second terminal or a scheduled task)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep running, polling for new jobs (worker daemon mode).",
        )
        parser.add_argument("--interval", type=int, default=5, help="Polling seconds in --loop mode.")
        parser.add_argument(
            "--resource-id",
            dest="resource_id",
            default=None,
            help="UUID of one resource: re-enqueue its full pipeline and process now.",
        )

    def handle(self, *args, **options):
        resource_id = options["resource_id"]
        if resource_id:
            resource = Resource.objects.filter(public_id=resource_id).first()
            if resource is None:
                raise self.error(f"No resource with public_id {resource_id}")
            enqueue(resource, ProcessingJob.Step.EXTRACT)
            job = enqueue(resource, ProcessingJob.Step.CHUNK)
            # CHUNK depends on EXTRACT; ensure ordering by draining twice.
            drain_queue()
            if job.status == ProcessingJob.Status.PENDING:
                drain_queue()
            self.stdout.write(self.style.SUCCESS(f"Processed pipeline for {resource.title}"))
            return

        if options["loop"]:
            interval = options["interval"]
            self.stdout.write(self.style.SUCCESS("Worker started; Ctrl+C to stop."))
            while True:
                count = drain_queue()
                if count:
                    self.stdout.write(self.style.SUCCESS(f"Processed {count} job(s)."))
                time.sleep(interval)
        else:
            count = drain_queue()
            self.stdout.write(self.style.SUCCESS(f"Processed {count} job(s)."))
