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