"""Audit logging for privileged actions (AGENTS.md section 6).

Append-only: rows are written here and never modified through the admin.
Call sites live in the admin config / management commands - never in
business services that are exercised by normal read/write flows.
"""

from common.models import AuditEvent


def record(*, actor=None, action, target_type="", target_id="", detail=""):
    """Append one AuditEvent. actor is a User (may be None for system flows)."""
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type=target_type[:40],
        target_id=str(target_id)[:64],
        detail=detail[:4000],
    )