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
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )

    def __str__(self):
        return self.get_full_name() or self.username

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
