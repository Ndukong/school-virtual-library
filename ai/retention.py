"""AI history retention (WP9 safeguarding/privacy).

Settings: AI_RETENTION_DAYS is the retention window in days; 0 (the default)
disables automatic retention and the purge command refuses to run without an
explicit --days, so history is never deleted by default.

Deletion covers AIInteraction and AIGeneration rows (the student-facing Q&A
and study material). AIRequestLog cost/budget rows are deliberately KEPT: the
per-school budget ledger must not shrink when content is forgotten.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from ai.models import AIGeneration, AIInteraction


def _cutoff(days):
    return timezone.now() - timedelta(days=max(1, int(days)))


def purge_ai_history(days=None, dry_run=False):
    """Delete AI history older than the window.

    Returns {"cutoff": <datetime>, "interactions": n, "generations": n}.
    Raises ValueError when retention is disabled and no explicit days given.
    """
    if days is None:
        days = int(getattr(settings, "AI_RETENTION_DAYS", 0) or 0)
        if days <= 0:
            raise ValueError(
                "Automatic retention is disabled (AI_RETENTION_DAYS=0); "
                "pass --days to purge explicitly."
            )
    cutoff = _cutoff(days)
    interactions = AIInteraction.objects.filter(created_at__lt=cutoff)
    generations = AIGeneration.objects.filter(created_at__lt=cutoff)
    result = {
        "cutoff": cutoff,
        "interactions": interactions.count(),
        "generations": generations.count(),
    }
    if not dry_run:
        interactions.delete()
        generations.delete()
    return result