"""Shared AI rate limiting across all AI features (AGENTS.md section 14)."""

from django.conf import settings
from django.utils import timezone


class RateLimited(Exception):
    """Raised when the user exceeds AI_RATE_LIMIT_PER_MINUTE."""


def recent_ai_request_count(user, minutes=1):
    """Count this user's AI interactions AND study generations in the window."""
    since = timezone.now() - timezone.timedelta(minutes=minutes)
    from ai.models import AIGeneration, AIInteraction

    interactions = AIInteraction.objects.filter(user=user, created_at__gte=since).count()
    generations = AIGeneration.objects.filter(user=user, created_at__gte=since).count()
    return interactions + generations


def enforce(user):
    limit = getattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 10)
    if not user.is_superuser and recent_ai_request_count(user) >= limit:
        raise RateLimited("AI usage limit reached for this minute; please wait.")
