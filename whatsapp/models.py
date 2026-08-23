"""WhatsApp channel models (AGENTS.md section 19, SKILLS.md section 20).

WhatsApp is an INTERFACE, not the database: all domain logic lives in the
existing service modules. These models handle only the channel's plumbing:
link codes, per-phone session state, and a message log with dedupe.
"""


from django.conf import settings
from django.db import models
from django.utils import timezone


class WhatsAppLink(models.Model):
    """An expiring code that binds a phone number to a user account.

    Phone numbers are never trusted on their own: only a code generated for
    the authenticated user (web UI or management command) can bind a number.
    """

    code = models.CharField(max_length=12, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="whatsapp_links"
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-expires_at"]

    def is_valid(self):
        return self.used_at is None and timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.code} -> {self.user}"


class WhatsAppSession(models.Model):
    """Per-phone session state; stores the linked user and thin menu context."""

    phone_number = models.CharField(max_length=20, unique=True)
    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_sessions",
    )
    state = models.CharField(max_length=24, default="MENU")
    context = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.phone_number} -> {self.linked_user}"

    def linked(self):
        return self.linked_user_id is not None

    def clean(self):
        super().clean()
        if self.phone_number:
            if not self.phone_number.startswith("+"):
                self.phone_number = f"+{self.phone_number}"


class WhatsAppMessage(models.Model):
    """Deduped log of inbound messages (provider retries same wamid)."""

    message_id = models.CharField(max_length=120, unique=True, db_index=True)
    phone_number = models.CharField(max_length=20, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    direction = models.CharField(max_length=4, default="IN")  # IN / OUT
    body = models.TextField(blank=True)
    handled_ok = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone_number", "created_at"]),
        ]

    def __str__(self):
        return f"{self.direction} {self.phone_number}: {self.body[:40]}"