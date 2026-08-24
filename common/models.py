from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base adding creation and last-update timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditEvent(models.Model):
    """Governance trail for privileged actions (AGENTS.md section 6).

    Records *who* performed *what* on *which target* so a school or the
    platform can reconstruct sensitive actions: admin resource deletion,
    user role/status changes by an administrator, and user account deletion.
    Written only through common.audit.record(). Read-only for everyone; even
    superusers cannot edit or delete rows (append-only).
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_actions",
    )
    # A stable action key, e.g. "user.admin_change" / "resource.admin_delete".
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Lists (not tuples) match Django 5.2's autodetector/migration
        # serialisation; tuples here would never be detected as "no change".
        ordering = ["-created_at"]  # noqa: RUF012 - idiomatic Django; see below
        indexes = [  # noqa: RUF012 - idiomatic Django; see below
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
        ]

    def __str__(self):
        target = f" {self.target_type}:{self.target_id}" if self.target_id else ""
        actor = self.actor.get_username() if self.actor else "(system)"
        return f"{self.created_at:%Y-%m-%d %H:%M} {actor} {self.action}{target}"