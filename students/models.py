from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from classes.models import SchoolClass
from common.models import TimeStampedModel
from schools.models import School


class Student(TimeStampedModel):
    """Student domain profile attached to an auth user.

    Deliberately minimal: no sensitive personal data beyond the admission
    number needed to identify the student within their school.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
        limit_choices_to={"role": "STUDENT"},
    )
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="students")
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="students",
    )
    admission_number = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school__name", "admission_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "admission_number"],
                name="unique_admission_number_per_school",
            ),
        ]

    def __str__(self):
        return f"{self.user} ({self.admission_number})"

    def save(self, *args, **kwargs):
        # Enforce cross-model invariants at save time as well: admin inlines
        # assign the user link after form validation, which would otherwise
        # bypass clean().
        self.clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors = {}
        if self.user_id and self.user.role != "STUDENT":
            errors["user"] = "A student profile requires a user with the Student role."
        if self.user_id and self.school_id and self.user.school_id != self.school_id:
            errors["school"] = "The student's profile must belong to the same school as their user account."
        if self.school_class and self.school_id and self.school_class.school_id != self.school_id:
            errors["school_class"] = "The class must belong to the student's school."
        elif (
            self.school_class
            and not self.school_id
            and self.user_id
            and self.user.school_id != self.school_class.school_id
        ):
            errors["school_class"] = "The class must belong to the student's school."
        if errors:
            raise ValidationError(errors)