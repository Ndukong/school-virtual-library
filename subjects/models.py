from django.db import models

from common.models import TimeStampedModel
from schools.models import School


class Subject(TimeStampedModel):
    """A subject taught at a school, e.g. Physics or History."""

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="subjects")
    name = models.CharField(max_length=150)
    # Nullable so that schools without codes can leave it empty; multiple
    # NULLs never violate the uniqueness constraint.
    code = models.CharField(max_length=30, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_subject_name_per_school"),
            models.UniqueConstraint(fields=["school", "code"], name="unique_subject_code_per_school"),
        ]

    def __str__(self):
        if self.code:
            return f"{self.name} ({self.code})"
        return self.name