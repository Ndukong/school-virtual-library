"""Per-school AI budgets (WP5) enforced on top of AIRequestLog.

Daily and monthly ceilings for both request counts and tokens (where the
provider reports them). A BudgetExceeded is a RateLimited subclass so the
existing views and WhatsApp handler already translate it into a friendly,
safe message.
"""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from ai.models import AIRequestLog
from ai.ratelimit import RateLimited


class BudgetExceeded(RateLimited):
    """Raised when a school exceeds an AI budget window."""


def _local_now():
    tz = ZoneInfo(getattr(settings, "TIME_ZONE", "UTC"))
    return timezone.now().astimezone(tz)


def _window_start(which):
    """Local-time anchoring for 'day' or 'month' window, as aware UTC."""
    local = _local_now()
    if which == "month":
        start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(ZoneInfo("UTC"))


def usage(school):
    """Recent request/token usage for a school (local day and month)."""
    today_start = _window_start("day")
    month_start = _window_start("month")
    log = AIRequestLog.objects.filter(school=school)
    today = log.filter(created_at__gte=today_start)
    month = log.filter(created_at__gte=month_start)
    return {
        "day_requests": today.count(),
        "month_requests": month.count(),
        "day_tokens": today.aggregate(sum=Sum("tokens_in") + Sum("tokens_out"))["sum"] or 0,
        "month_tokens": month.aggregate(sum=Sum("tokens_in") + Sum("tokens_out"))["sum"] or 0,
    }


def caps():
    return {
        "day_requests": getattr(settings, "AI_BUDGET_DAILY_REQUESTS", 0),
        "month_requests": getattr(settings, "AI_BUDGET_MONTHLY_REQUESTS", 0),
        "day_tokens": getattr(settings, "AI_BUDGET_DAILY_TOKENS", 0),
        "month_tokens": getattr(settings, "AI_BUDGET_MONTHLY_TOKENS", 0),
    }


def enforce_budget(school):
    """Raise BudgetExceeded if any window is over its ceiling."""
    current = usage(school)
    limits = caps()
    breaches = []
    if limits["day_requests"] and current["day_requests"] >= limits["day_requests"]:
        breaches.append(f"daily request budget ({limits['day_requests']}) reached")
    if limits["month_requests"] and current["month_requests"] >= limits["month_requests"]:
        breaches.append(f"monthly request budget ({limits['month_requests']}) reached")
    if limits["day_tokens"] and current["day_tokens"] >= limits["day_tokens"]:
        breaches.append("daily token budget reached")
    if limits["month_tokens"] and current["month_tokens"] >= limits["month_tokens"]:
        breaches.append("monthly token budget reached")
    if breaches:
        raise BudgetExceeded(
            "School AI budget reached this period; usage resumes when the "
            "window resets. " + "; ".join(breaches)
        )