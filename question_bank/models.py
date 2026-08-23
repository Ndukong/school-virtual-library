"""Question bank models (AGENTS.md section 15, SKILLS.md sections 10/12).

Questions carry rich metadata (subject/class/topic/Bloom/difficulty/marks),
an answer and marking scheme, full source traceability, and an approval
workflow. Only APPROVED questions may be used by the examination generator;
AI-imported questions always land in the review queue and are never
auto-approved.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from classes.models import SchoolClass
from common.models import TimeStampedModel
from library.models import BookChapter, Resource
from schools.models import School
from subjects.models import Subject


class Question(TimeStampedModel):
    class QuestionType(models.TextChoices):
        MCQ = "MCQ", "Multiple choice"
        TRUE_FALSE = "TRUE_FALSE", "True/False"
        SHORT_STRUCTURED = "SHORT_STRUCTURED", "Short structural"
        STRUCTURED = "STRUCTURED", "Structured"
        GROUPED_STRUCTURED = "GROUPED_STRUCTURED", "Grouped structural"
        ESSAY = "ESSAY", "Essay"
        CALCULATION = "CALCULATION", "Calculation"
        PRACTICAL = "PRACTICAL", "Practical"
        OTHER = "OTHER", "Other"

    class Difficulty(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    class BloomLevel(models.TextChoices):
        KNOWLEDGE = "KNOWLEDGE", "Knowledge"
        COMPREHENSION = "COMPREHENSION", "Comprehension"
        APPLICATION = "APPLICATION", "Application"
        ANALYSIS = "ANALYSIS", "Analysis"
        SYNTHESIS = "SYNTHESIS", "Synthesis"
        EVALUATION = "EVALUATION", "Evaluation"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="questions")
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, null=True, blank=True, related_name="questions"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions"
    )
    topic = models.CharField(max_length=150)
    subtopic = models.CharField(max_length=150, blank=True)

    question_type = models.CharField(
        max_length=20, choices=QuestionType.choices, default=QuestionType.SHORT_STRUCTURED
    )
    difficulty = models.CharField(
        max_length=10, choices=Difficulty.choices, default=Difficulty.MEDIUM
    )
    marks = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    bloom_level = models.CharField(
        max_length=15, choices=BloomLevel.choices, default=BloomLevel.KNOWLEDGE
    )

    body = models.TextField()
    options = models.JSONField(null=True, blank=True)  # MCQ/TF choices
    correct_answer = models.TextField()
    marking_scheme = models.TextField(blank=True)

    # Source traceability.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_questions"
    )
    source_resource = models.ForeignKey(
        Resource, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions"
    )
    chapter = models.ForeignKey(
        BookChapter, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions"
    )
    page_number = models.PositiveIntegerField(null=True, blank=True)
    ai_generation = models.ForeignKey(
        "ai.AIGeneration", on_delete=models.SET_NULL, null=True, blank=True, related_name="questions"
    )

    approval_status = models.CharField(
        max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_questions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Fields whose change invalidates a previous approval.
    CONTENT_FIELDS = (
        "body", "options", "correct_answer", "marking_scheme", "marks",
        "question_type", "difficulty", "bloom_level", "topic", "subtopic",
    )

    class Meta:
        ordering = ["school__name", "subject__name", "topic", "-created_at"]
        indexes = [
            models.Index(fields=["school", "approval_status"]),
            models.Index(fields=["school", "subject", "topic"]),
            models.Index(fields=["school", "question_type", "difficulty"]),
        ]

    def __str__(self):
        return f"{self.get_question_type_display()} ({self.marks}m): {self.body[:60]}"

    def clean(self):
        super().clean()
        errors = {}
        if self.author_id and self.school_id and not self.author.is_superuser:
            if self.author.school_id != self.school_id:
                errors["school"] = "The author must belong to the question's school."
        if self.subject and self.school_id and self.subject.school_id != self.school_id:
            errors["subject"] = "The subject must belong to the question's school."
        if (
            self.school_class
            and self.school_id
            and self.school_class.school_id != self.school_id
        ):
            errors["school_class"] = "The class must belong to the question's school."
        if self.source_resource and self.school_id and self.source_resource.school_id != self.school_id:
            errors["source_resource"] = "The source resource must belong to the question's school."
        if not self.body.strip():
            errors["body"] = "Question body is required."
        if not self.correct_answer.strip():
            errors["correct_answer"] = "An answer is required."
        # Validators run only in full_clean(); enforce marks bounds here so
        # programmatic saves cannot bypass them.
        if self.marks is None or not 1 <= self.marks <= 100:
            errors["marks"] = "Marks must be between 1 and 100."
        if self.question_type == self.QuestionType.MCQ:
            if not isinstance(self.options, list) or len(self.options) < 2 or \
                    any(not str(option).strip() for option in self.options):
                errors["options"] = "MCQ questions need at least two non-empty options."
        elif self.question_type == self.QuestionType.TRUE_FALSE:
            if not self.options:
                self.options = ["True", "False"]
            elif set(map(str, self.options)) != {"True", "False"}:
                errors["options"] = "True/False options must be exactly True and False."
        else:
            self.options = None
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(*self.CONTENT_FIELDS).first()
            if previous and any(previous[field] != getattr(self, field) for field in self.CONTENT_FIELDS):
                # Editing content invalidates a prior approval (SKILLS.md 12).
                self.approval_status = self.ApprovalStatus.DRAFT
                self.approved_by = None
                self.approved_at = None
                self.review_notes = ""
        self.clean()
        super().save(*args, **kwargs)