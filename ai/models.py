"""AI usage tracking and interaction audit (AGENTS.md sections 14/28)."""

import uuid

from django.conf import settings
from django.db import models


class AIRequestLog(models.Model):
    """One row per outbound AI call, successful or not."""

    class Kind(models.TextChoices):
        EMBED = "EMBED", "Embedding"
        GENERATE = "GENERATE", "Generation"

    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    ok = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    input_items = models.PositiveIntegerField(default=1)
    tokens_in = models.PositiveIntegerField(null=True, blank=True)
    tokens_out = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "model", "kind"]),
        ]

    def __str__(self):
        status = "ok" if self.ok else "error"
        return f"{self.provider}/{self.model} {self.kind} [{status}]"


class AIInteraction(models.Model):
    """One ask-the-librarian question/answer pair, kept for audit and abuse
    monitoring. Answers cite only sources retrieved for that question."""

    class Scope(models.TextChoices):
        GENERAL = "GENERAL", "General AI"
        LIBRARY = "LIBRARY", "Whole library"
        SUBJECT = "SUBJECT", "Subject"
        CLASS = "CLASS", "Class/form"
        BOOK = "BOOK", "Book"
        CHAPTER = "CHAPTER", "Chapter"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_interactions"
    )
    school = models.ForeignKey(
        "schools.School", on_delete=models.PROTECT, null=True, blank=True, related_name="ai_interactions"
    )
    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.LIBRARY)
    question = models.TextField()
    answer = models.TextField(blank=True)
    model = models.CharField(max_length=120, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    cited_chunk_ids = models.JSONField(default=list, blank=True)
    retrieved_count = models.PositiveSmallIntegerField(default=0)
    used_provider = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["school", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user}: {self.question[:60]}"


class AIGeneration(models.Model):
    """AI-generated study material (summaries, notes, questions, ...).

    These are study SUPPORT artifacts, clearly AI-generated; they never enter
    the approved question bank or replace teacher-authored content.
    """

    class Kind(models.TextChoices):
        SUMMARY = "SUMMARY", "Summary"
        REVISION_NOTES = "REVISION_NOTES", "Revision notes"
        DEFINITIONS_FORMULAE = "DEFINITIONS_FORMULAE", "Definitions and formulae"
        PRACTICE_QUESTIONS = "PRACTICE_QUESTIONS", "Practice questions"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_generations"
    )
    school = models.ForeignKey(
        "schools.School", on_delete=models.PROTECT, null=True, blank=True, related_name="ai_generations"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    scope = models.CharField(max_length=12, choices=AIInteraction.Scope.choices)
    source_resource = models.ForeignKey(
        "library.Resource", on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_generations"
    )
    topic = models.CharField(max_length=300, blank=True)
    content = models.TextField()
    cited_chunk_ids = models.JSONField(default=list, blank=True)
    retrieved_count = models.PositiveSmallIntegerField(default=0)
    model = models.CharField(max_length=120, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    used_provider = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["school", "kind"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} for {self.user} ({self.scope})"
