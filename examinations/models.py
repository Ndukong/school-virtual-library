"""Examination models (AGENTS.md sections 16/17, SKILLS.md section 11).

An Exam is assembled from APPROVED question-bank items only, so its total is
always mathematically true. The configuration snapshot is stored for
actual-vs-requested reporting (topics, Bloom distribution).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from classes.models import SchoolClass
from common.models import TimeStampedModel
from question_bank.models import Question
from schools.models import School
from subjects.models import Subject


class Exam(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft (assembling)"
        READY_FOR_REVIEW = "READY_FOR_REVIEW", "Ready for review"
        PUBLISHED = "PUBLISHED", "Published"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="exams")
    title = models.CharField(max_length=255)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="exams")
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL, null=True, blank=True, related_name="exams"
    )
    duration_minutes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(5), MaxValueValidator(600)]
    )
    total_marks = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(500)]
    )
    instructions = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_exams"
    )
    # Snapshot of the generation request: topics, question types, bloom
    # distribution percentages, difficulty preferences. Used for the
    # actual-vs-requested validation report; never edited after creation.
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["school__name", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.total_marks}m, {self.get_status_display()})"

    def clean(self):
        super().clean()
        errors = {}
        if self.subject and self.school_id and self.subject.school_id != self.school_id:
            errors["subject"] = "The subject must belong to the exam's school."
        if (
            self.school_class
            and self.school_id
            and self.school_class.school_id != self.school_id
        ):
            errors["school_class"] = "The class must belong to the exam's school."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def achieved_marks(self):
        return sum(eq.marks for eq in self.exam_questions.select_related("question"))


class ExamQuestion(TimeStampedModel):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="exam_questions")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="exam_slots")
    position = models.PositiveSmallIntegerField()
    marks = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

    class Meta:
        ordering = ["exam", "position"]
        constraints = [
            models.UniqueConstraint(fields=["exam", "question"], name="unique_question_per_exam"),
        ]

    def __str__(self):
        return f"{self.exam.title} #{self.position}: {self.question}"

    def clean(self):
        super().clean()
        errors = {}
        if self.exam_id and self.question_id and self.exam.school_id != self.question.school_id:
            errors["question"] = "Questions must belong to the exam's school."
        if (
            self.exam_id
            and self.question_id
            and self.question.approval_status != Question.ApprovalStatus.APPROVED
        ):
            errors["question"] = "Only approved questions may appear on an exam."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)