"""Shared AI rate limiting across all AI features (AGENTS.md section 14).

Two paths, selected by AI_RATE_LIMIT_USE_CACHE:
- cache: atomic per-minute counter via cache.incr (safe under concurrency on
  a shared cache; locmem in dev is per-process), with a database-count
  fallback if the cache is unavailable.
- database: count of AIInteraction + AIGeneration rows in the window. Kept
  as the deterministic path for the test suite (settings_test) and as the
  fallback when the cache backend errors.

Superusers are only exempt when AI_RATE_LIMIT_EXEMPT_SUPERUSER is enabled -
there is no unconditional exemption.
"""

import time

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from ai.models import AIGeneration, AIInteraction


class RateLimited(Exception):
    """Raised when the user exceeds AI_RATE_LIMIT_PER_MINUTE."""


def recent_ai_request_count(user, minutes=1):
    """Count this user's AI interactions AND study generations in the window."""
    since = timezone.now() - timezone.timedelta(minutes=minutes)
    interactions = AIInteraction.objects.filter(user=user, created_at__gte=since).count()
    generations = AIGeneration.objects.filter(user=user, created_at__gte=since).count()
    return interactions + generations


def _db_count(user):
    return recent_ai_request_count(user) + 1


def _cache_count(user, window_bucket):
    key = f"ai-rate:{user.pk}:{window_bucket}"
    try:
        return cache.incr(key)
    except ValueError:
        # First use in this window: seed the counter.
        try:
            cache.add(key, 1, timeout=120)
        except Exception:  # noqa: BLE001 - DB fallback below
            return _db_count(user)
        return 1
    except Exception:  # noqa: BLE001 - cache down: fall back to DB count
        return _db_count(user)


def enforce(user):
    limit = getattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 10)
    if getattr(settings, "AI_RATE_LIMIT_EXEMPT_SUPERUSER", False) and user.is_superuser:
        return

    if getattr(settings, "AI_RATE_LIMIT_USE_CACHE", True):
        window_bucket = int(time.time() // 60)
        count = _cache_count(user, window_bucket)
    else:
        count = _db_count(user)

    if count > limit:
        raise RateLimited("AI usage limit reached for this minute; please wait.")