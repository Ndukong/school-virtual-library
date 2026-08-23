"""Shared views: unauthenticated liveness/health probe.

/healthz/ reports database and processing-queue health for load balancers
and monitoring. It is intentionally unauthenticated, returns no data, and
never leaks error details.
"""

import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    status = {"database": "ok", "queue_pending": None}
    http_code = 200

    try:
        connection.ensure_connection()
    except Exception:
        logger.error("healthz: database unreachable", exc_info=True)
        status["database"] = "unavailable"
        http_code = 503

    if status["database"] == "ok":
        try:
            from documents.models import ProcessingJob

            status["queue_pending"] = ProcessingJob.objects.filter(
                status=ProcessingJob.Status.PENDING
            ).count()
        except Exception:
            logger.error("healthz: queue unavailable", exc_info=True)
            status["queue_pending"] = "unavailable"
            http_code = 503

    return JsonResponse(status, status=http_code)