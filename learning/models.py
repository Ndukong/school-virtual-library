"""Student practice models (AGENTS.md section 18).

Attempts belong to exactly one student and are never visible to other
students. Answers are withheld until the attempt is submitted; objective
questions (MCQ/True-False) are auto-graded, others await teacher-scheme
self-review by the student.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import TimeStampedModel
from examinations.models import Exam
from question_bank.models import Question
from schools.models import School
from subjects.models import Subject


class PracticeAttempt(TimeStampedModel):
    class Source(models.TextChoices):
        SELF_QUIZ = "SELF_QUIZ", "Self quiz"
        PUBLISHED_EXAM = "PUBLISHED_EXAM", "Published exam"

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        SUBMITTED = "SUBMITTED", "Submitted"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="practice_attempts",
        limit_choices_to={"role": "STUDENT"},
    )
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="practice_attempts")
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="practice_attempts"
    )
    source_type = models.CharField(max_length=16, choices=Source.choices, default=Source.SELF_QUIZ)
    exam = models.ForeignKey(
        Exam, on_delete=models.SET_NULL, null=True, blank=True, related_name="practice_attempts"
    )
    topic_filter = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    possible_marks = models.PositiveIntegerField(default=0)
    earned_marks = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["school", "created_at"]),
        ]

    def __str__(self):
        return f"{self.student} {self.get_source_display()} ({self.status})"

    def clean(self):
        super().clean()
        errors = {}
        if self.student_id and self.student.role != "STUDENT":
            errors["student"] = "Practice attempts belong to students."
        if self.student_id and self.school_id and self.student.school_id != self.school_id:
            errors["school"] = "The attempt's school must match the student's school."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def score_percent(self):
        if not self.possible_marks:
            return 0.0
        return round(self.earned_marks * 100.0 / self.possible_marks, 1)


class AttemptResponse(TimeStampedModel):
    attempt = models.ForeignKey(
        PracticeAttempt, on_delete=models.CASCADE, related_name="responses"
    )
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="attempt_responses")
    position = models.PositiveSmallIntegerField()
    given_answer = models.TextField(blank=True)
    is_correct = models.BooleanField(null=True, blank=True)  # None = awaiting grading/self-mark
    awarded_marks = models.PositiveSmallIntegerField(default=0)
    self_marked = models.BooleanField(default=False)

    class Meta:
        ordering = ["attempt", "position"]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="unique_question_per_attempt"),
        ]

    def __str__(self):
        return f"{self.attempt} #{self.position}"