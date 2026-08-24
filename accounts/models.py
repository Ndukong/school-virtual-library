from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom auth user scoped to a school with a single primary role.

    Roles are mutually exclusive, so a role field plus centralized permission
    helpers is used instead of Django groups for now. The default role is the
    least privileged one (Student); elevation happens explicitly.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    # UI + AI answer language (WP7). Stays in sync with LANGUAGES; set from the
    # header language switcher, defaulted to English.
    language = models.CharField(
        max_length=10, choices=settings.LANGUAGES, default="en"
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    # Set by admins after a temporary-password reset; login redirects to the
    # forced password change until cleared (WP3).
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return self.get_full_name() or self.username


class PasswordReset(models.Model):
    """Audit record of an admin-issued password reset and its completion."""

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_resets"
    )
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_password_resets"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "completed" if self.completed_at else "pending"
        return f"{self.admin_user} reset {self.target_user} ({status})"

class LoginFailure(models.Model):
    """Audit record of a failed login attempt (WP3 lockout trail)."""

    username = models.CharField(max_length=150, db_index=True)
    ip = models.GenericIPAddressField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["username", "ip", "created_at"]),
        ]

    def __str__(self):
        return f"{self.username} from {self.ip} @ {self.created_at:%Y-%m-%d %H:%M}"


class LoginLock(models.Model):
    """Exponential-backoff lock keyed on username AND IP."""

    username = models.CharField(max_length=150)
    ip = models.GenericIPAddressField()
    attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["username", "ip"], name="unique_login_lock_key"),
        ]

    def __str__(self):
        return f"{self.username} @ {self.ip} ({self.attempts} attempt(s))"
