from django.db import models

from common.models import TimeStampedModel


class School(TimeStampedModel):
    """A school tenant. All school-scoped data hangs off this model."""

    name = models.CharField(max_length=200, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "schools"

    def __str__(self):
        return self.name