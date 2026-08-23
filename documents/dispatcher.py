"""Job dispatch and execution.

Enqueueing creates or re-arms a ProcessingJob. Workers claim jobs with an
atomic conditional UPDATE (safe on SQLite and PostgreSQL). Inline mode runs
jobs synchronously at enqueue time for tests and small deployments; the
default path leaves work in the queue for `process_documents`.
"""

from django.conf import settings
from django.db import transaction

from documents.models import ProcessingJob, ProcessingLog
from documents.services import (
    PipelineError,
    execute_step,
    log_event,
    set_processing_status,
    utcnow,
)
from library.models import Resource


def enqueue(resource, step):
    """Create or re-arm the job for (resource, step); run inline if configured."""
    job, created = ProcessingJob.objects.get_or_create(
        resource=resource,
        step=step,
        defaults={
            "max_attempts": getattr(settings, "DOCUMENTS_MAX_ATTEMPTS", 3),
        },
    )
    if not created and job.status in (
        ProcessingJob.Status.FAILED,
        ProcessingJob.Status.SUCCEEDED,
    ):
        job.status = ProcessingJob.Status.PENDING
        job.last_error = ""
        job.finished_at = None
        job.save(update_fields=["status", "last_error", "finished_at", "updated_at"])
    if getattr(settings, "DOCUMENTS_INLINE_PROCESSING", False):
        process_job(job)
    return job


def claim_next_job():
    """Atomically claim the oldest pending job, or return None."""
    with transaction.atomic():
        candidate = (
            ProcessingJob.objects.filter(status=ProcessingJob.Status.PENDING)
            .select_related("resource")
            .order_by("created_at")
            .first()
        )
        if candidate is None:
            return None
        claimed = ProcessingJob.objects.filter(
            pk=candidate.pk, status=ProcessingJob.Status.PENDING
        ).update(status=ProcessingJob.Status.RUNNING, started_at=utcnow())
    if not claimed:
        return None  # another worker won the race
    candidate.refresh_from_db(fields=["status", "started_at"])
    return candidate


def process_job(job):
    """Execute one claimed job, applying retry/failure bookkeeping."""
    job.attempts += 1
    job.save(update_fields=["attempts", "updated_at"])
    try:
        execute_step(job)
    except PipelineError as exc:
        _handle_failure(job, str(exc))
        return job
    except Exception as exc:  # noqa: BLE001 - worker must survive any task error
        _handle_failure(job, f"Unexpected error: {exc}")
        return job
    job.status = ProcessingJob.Status.SUCCEEDED
    job.finished_at = utcnow()
    job.last_error = ""
    job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
    return job


def _handle_failure(job, message):
    if job.attempts >= job.max_attempts:
        job.status = ProcessingJob.Status.FAILED
    else:
        # Back to PENDING for another attempt by any worker.
        job.status = ProcessingJob.Status.PENDING
    job.last_error = message[:5000]
    job.finished_at = utcnow() if job.status == ProcessingJob.Status.FAILED else None
    job.save(update_fields=["status", "last_error", "finished_at", "updated_at"])
    log_event(job.resource, ProcessingLog.Level.ERROR, message)
    # Surface the failure on the resource immediately (even while retries are
    # pending); a successful retry overwrites the status afterwards.
    set_processing_status(job.resource, Resource.ProcessingStatus.FAILED)


def drain_queue(limit=100):
    """Process pending jobs until the queue is empty. Returns count."""
    processed = 0
    while processed < limit:
        job = claim_next_job()
        if job is None:
            break
        process_job(job)
        processed += 1
    return processed