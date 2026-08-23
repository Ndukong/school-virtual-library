"""Library services: untrusted-upload validation and access control.

Uploaded documents are untrusted input (AGENTS.md sections 15/21). Validation
checks extension, size, and the actual file signature rather than trusting
client-supplied types. Access rules are centralized here so views, templates,
and future APIs share one implementation.
"""

import os

from django.conf import settings
from django.core.exceptions import ValidationError

from accounts.permissions import is_admin
from library.models import Resource

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