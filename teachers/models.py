from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import TimeStampedModel
from schools.models import School
from subjects.models import Subject


class Teacher(TimeStampedModel):
    """Teacher domain profile attached to an auth user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        limit_choices_to={"role": "TEACHER"},
    )
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="teachers")
    staff_number = models.CharField(max_length=50, null=True, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name="teachers")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "staff_number"],
                name="unique_staff_number_per_school",
            ),
        ]

    def __str__(self):
        return f"{self.user}{f' ({self.staff_number})' if self.staff_number else ''}"

    def save(self, *args, **kwargs):
        # Enforce cross-model invariants at save time as well: admin inlines
        # assign the user link after form validation, which would otherwise
        # bypass clean().
        self.clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors = {}
        if self.user_id and self.user.role != "TEACHER":
            errors["user"] = "A teacher profile requires a user with the Teacher role."
        if self.user_id and self.school_id and self.user.school_id != self.school_id:
            errors["school"] = "The teacher's profile must belong to the same school as their user account."
        if self.school_id and self.pk:
            foreign_subjects = self.subjects.exclude(school_id=self.school_id).count()
            if foreign_subjects:
                errors["subjects"] = "All subjects must belong to the teacher's school."
        elif self.school_id and not self.pk:
            # M2M cannot be checked before the first save; validated post-save
            # by forms/admin via clean_fields on the through table instead.
            pass
        if errors:
            raise ValidationError(errors)