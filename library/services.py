"""Library services: untrusted-upload validation and access control.

Uploaded documents are untrusted input (AGENTS.md sections 15/21). Validation
checks extension, size, and the actual file signature rather than trusting
client-supplied types. Access rules are centralized here so views, templates,
and future APIs share one implementation.
"""

import os
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

from accounts.permissions import is_admin
from library.models import Resource, ResourceAccessEvent

PDF_MAGIC = b"%PDF-"
MAX_SNIFF_BYTES = 8 * 1024
ALLOWED_EXTENSIONS = {".pdf"}


def validate_upload(uploaded_file):
    """Validate an uploaded document. Raises ValidationError on any failure."""
    errors = []

    max_mb = getattr(settings, "LIBRARY_MAX_UPLOAD_MB", 100)
    if uploaded_file.size > max_mb * 1024 * 1024:
        errors.append(f"File exceeds the maximum allowed size of {max_mb} MB.")

    name = uploaded_file.name or ""
    extension = os.path.splitext(name)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        errors.append("Only PDF files are accepted in this phase.")
        raise ValidationError(errors)

    signature = uploaded_file.read(MAX_SNIFF_BYTES)
    uploaded_file.seek(0)
    if not signature.startswith(PDF_MAGIC):
        errors.append("File content does not look like a valid PDF document.")
        raise ValidationError(errors)

    if errors:
        raise ValidationError(errors)


def user_can_read_resource(user, resource):
    """Centralized read rule for a single resource."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if resource.school_id != user.school_id:
        return False
    if is_admin(user):
        # School administrators may access everything in their school,
        # including inactive resources awaiting moderation.
        return True
    if user.role == "TEACHER":
        return True
    if user.role == "STUDENT":
        return (
            resource.is_active
            and resource.access_policy == Resource.AccessPolicy.SCHOOL
        )
    return False


def visible_resources(user):
    """Queryset of resources the user may list/read, scoped to their school."""
    queryset = Resource.objects.select_related("subject", "school_class", "uploaded_by")
    if not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if not user.school_id:
        return queryset.none()
    queryset = queryset.filter(school_id=user.school_id)
    if user.role == "STUDENT":
        queryset = queryset.filter(
            is_active=True, access_policy=Resource.AccessPolicy.SCHOOL
        )
    return queryset

def _local_day_start():
    """Start of today in the application timezone, as an aware UTC instant."""
    tz = ZoneInfo(getattr(settings, "TIME_ZONE", "UTC"))
    local = timezone.now().astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(ZoneInfo("UTC"))


def download_exceeded(user):
    """Return 'burst' / 'daily' / None when a user exceeds download limits.

    Enforced against ResourceAccessEvent (WP3) in LOCAL-time day boundaries.
    Superusers are exempt so operational staff are never cut off.
    """
    if getattr(user, "is_superuser", False):
        return None
    minute_ago = timezone.now() - timezone.timedelta(minutes=1)
    events = ResourceAccessEvent.objects
    burst = events.filter(
        user=user,
        kind=ResourceAccessEvent.Kind.DOWNLOAD,
        created_at__gte=minute_ago,
    ).count()
    if burst >= getattr(settings, "LIBRARY_DOWNLOAD_PER_MINUTE", 10):
        return "burst"
    daily = events.filter(
        user=user,
        kind=ResourceAccessEvent.Kind.DOWNLOAD,
        created_at__gte=_local_day_start(),
    ).count()
    if daily >= getattr(settings, "LIBRARY_DOWNLOAD_DAILY_CAP", 50):
        return "daily"
    return None


def storage_quota_state(school):
    """Current school storage usage in bytes plus the configured cap."""
    used = (
        Resource.objects.filter(school=school)
        .exclude(file_size__isnull=True)
        .aggregate(total=Sum("file_size"))["total"]
        or 0
    )
    cap = getattr(settings, "SCHOOL_STORAGE_QUOTA_MB", 5000) * 1024 * 1024
    return {"used": used, "cap": cap}


def upload_within_quota(school, incoming_bytes):
    """True when incoming_bytes fits inside the school storage quota."""
    state = storage_quota_state(school)
    if not state["cap"]:
        return True
    return state["used"] + incoming_bytes <= state["cap"]
