"""Document processing models.

Extraction results are stored separately from the original file, which is
never modified (AGENTS.md section 11). Every processing run is traceable:
jobs record attempts and outcomes, logs capture diagnostics for
administrators.
"""

import uuid

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel
from library.models import BookChapter, BookSection, Resource


class ExtractedPage(TimeStampedModel):
    """Text extracted from a single page of a resource."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="extracted_pages")
    page_number = models.PositiveIntegerField()
    text = models.TextField(blank=True)
    has_text = models.BooleanField(default=False)
    # OCR workflow (WP4): blank pages are flagged for OCR; confidence 0..1
    # records engine output (None when unknown). ocr_at enables resumability.
    needs_ocr = models.BooleanField(default=False)
    ocr_confidence = models.FloatField(null=True, blank=True)
    ocr_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["resource", "page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "page_number"], name="unique_page_per_resource"
            ),
        ]

    def __str__(self):
        return f"{self.resource.title} p.{self.page_number}"


class DocumentChunk(TimeStampedModel):
    """A chunk of extracted text anchored to pages and optional structure."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="chunks")
    chapter = models.ForeignKey(
        BookChapter, on_delete=models.SET_NULL, null=True, blank=True, related_name="chunks"
    )
    section = models.ForeignKey(
        BookSection, on_delete=models.SET_NULL, null=True, blank=True, related_name="chunks"
    )
    sequence = models.PositiveIntegerField()
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    text = models.TextField()

    class Meta:
        ordering = ["resource", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "sequence"], name="unique_chunk_sequence_per_resource"
            ),
        ]
        indexes = [
            models.Index(fields=["resource", "page_start"]),
        ]

    def __str__(self):
        preview = self.text[:50].replace("\n", " ")
        return f"{self.resource.title} #{self.sequence}: {preview}"


class ChunkEmbedding(TimeStampedModel):
    """Stored embedding vector for one chunk.

    Vectors are stored as JSON with their model name; a model change triggers
    re-embedding rather than mixing vector spaces. When PostgreSQL/pgvector is
    deployed this table becomes the pgvector column source of truth.
    """

    chunk = models.OneToOneField(
        DocumentChunk, on_delete=models.CASCADE, related_name="embedding"
    )
    model_name = models.CharField(max_length=120)
    dimensions = models.PositiveSmallIntegerField()
    vector = models.JSONField()

    def __str__(self):
        return f"{self.chunk} ({self.model_name})"


class ProcessingLog(TimeStampedModel):
    """Diagnostic log entries for document processing runs."""

    class Level(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="processing_logs")
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    message = models.TextField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["resource", "level"]),
        ]

    def __str__(self):
        return f"[{self.level}] {self.message[:80]}"


class ProcessingJob(TimeStampedModel):
    """One unit of background work for a resource.

    The queue is database-backed: workers claim jobs with an atomic
    conditional UPDATE, which is safe on both SQLite and PostgreSQL. When a
    Celery/Redis deployment becomes available, only the dispatcher needs to
    change; task functions live in documents.services.
    """

    class Step(models.TextChoices):
        EXTRACT = "EXTRACT", "Extract text"
        CHUNK = "CHUNK", "Chunk text"
        EMBED = "EMBED", "Embed chunks"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="processing_jobs")
    step = models.CharField(max_length=20, choices=Step.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(
        default=getattr(settings, "DOCUMENTS_MAX_ATTEMPTS", 3)
    )
    last_error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["resource", "step"], name="unique_job_per_step"),
        ]

    def __str__(self):
        return f"{self.resource.title} / {self.step} ({self.status})"
