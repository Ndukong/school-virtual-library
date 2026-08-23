from django.db import models

from common.models import TimeStampedModel
from schools.models import School


class SchoolClass(TimeStampedModel):
    """A class/form within a school, e.g. 'Form 1' or 'Grade 8'."""

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="classes")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_class_name_per_school"),
        ]

    def __str__(self):
        return f"{self.school.name} - {self.name}"