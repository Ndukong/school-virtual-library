"""Library domain models.

A Resource is any school learning material (book, notes, past paper, ...).
Books additionally carry chapters and sections so that later phases (document
processing, RAG) can attach extracted text and citations to the right place
in the book. Files are stored privately and served only through controlled
views; nothing here exposes media directly.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from classes.models import SchoolClass
from common.models import TimeStampedModel
from library.files import sanitize_original_filename
from schools.models import School
from subjects.models import Subject


class Resource(TimeStampedModel):
    """A school-scoped learning resource with full metadata."""

    class ResourceType(models.TextChoices):
        BOOK = "BOOK", "Book"
        NOTES = "NOTES", "Notes"
        PAST_PAPER = "PAST_PAPER", "Past paper"
        MARKING_SCHEME = "MARKING_SCHEME", "Marking scheme"
        PRACTICAL_GUIDE = "PRACTICAL_GUIDE", "Practical guide"
        OTHER = "OTHER", "Other"

    class LicensingStatus(models.TextChoices):
        OWNED = "OWNED", "Owned by school"
        LICENSED = "LICENSED", "Licensed"
        OPEN_ACCESS = "OPEN_ACCESS", "Open access"
        PUBLIC_DOMAIN = "PUBLIC_DOMAIN", "Public domain"
        TEACHER_CREATED = "TEACHER_CREATED", "Teacher created"
        SCHOOL_CREATED = "SCHOOL_CREATED", "School created"
        UNKNOWN = "UNKNOWN", "Unknown"

    class AccessPolicy(models.TextChoices):
        SCHOOL = "SCHOOL", "Whole school"
        TEACHERS_ONLY = "TEACHERS_ONLY", "Teachers only"

    # Full processing state machine (AGENTS.md section 11). States other than
    # UPLOADED are driven by the Phase 3 document-processing pipeline.
    class ProcessingStatus(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        VALIDATING = "VALIDATING", "Validating"
        EXTRACTING = "EXTRACTING", "Extracting text"
        OCR_PROCESSING = "OCR_PROCESSING", "OCR processing"
        CHUNKING = "CHUNKING", "Chunking"
        EMBEDDING = "EMBEDDING", "Generating embeddings"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    # Public identifier used in URLs; integer pk stays internal.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="resources")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    resource_type = models.CharField(
        max_length=20, choices=ResourceType.choices, default=ResourceType.BOOK
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="resources"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL, null=True, blank=True, related_name="resources"
    )

    # Bibliographic metadata (AGENTS.md section 10).
    author = models.CharField(max_length=200, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    edition = models.CharField(max_length=50, blank=True)
    isbn = models.CharField(max_length=20, blank=True)
    curriculum = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=30, blank=True, default="en")
    publication_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1450), MaxValueValidator(timezone.now().year + 1)],
    )

    # File storage. upload_to never includes user input beyond Django's own
    # name sanitization; original_filename is display-only metadata.
    file = models.FileField(upload_to="resources/%Y/%m/", null=True, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)

    licensing_status = models.CharField(
        max_length=20,
        choices=LicensingStatus.choices,
        default=LicensingStatus.UNKNOWN,
    )
    access_policy = models.CharField(
        max_length=20,
        choices=AccessPolicy.choices,
        default=AccessPolicy.SCHOOL,
    )
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.UPLOADED,
    )
    is_active = models.BooleanField(default=True)
    # WP4 OCR: set when any page remains unreadable (needs_ocr or
    # low-confidence OCR) so a teacher can review it.
    needs_teacher_review = models.BooleanField(default=False)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_resources"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "resource_type"]),
            models.Index(fields=["school", "access_policy"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("library-detail", args=[str(self.public_id)])

    def clean(self):
        super().clean()
        errors = {}
        if self.resource_type == self.ResourceType.BOOK and not self.file:
            errors["file"] = "Books require an uploaded file."
        if (
            self.uploaded_by_id
            and self.school_id
            and not self.uploaded_by.is_superuser
            and self.uploaded_by.school_id != self.school_id
        ):
            errors["school"] = "The uploader must belong to the resource's school."
        if self.subject and self.school_id and self.subject.school_id != self.school_id:
            errors["subject"] = "The subject must belong to the resource's school."
        if (
            self.school_class
            and self.school_id
            and self.school_class.school_id != self.school_id
        ):
            errors["school_class"] = "The class must belong to the resource's school."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Replacing the file invalidates any previous processing results.
        if self.pk and self.file:
            previous = type(self).objects.filter(pk=self.pk).values_list("file", flat=True).first()
            if previous and previous != self.file.name:
                self.processing_status = self.ProcessingStatus.UPLOADED
        self.clean()
        super().save(*args, **kwargs)

    def store_file(self, uploaded_file):
        """Attach an already-validated upload to this resource."""
        self.file.save(uploaded_file.name, uploaded_file, save=False)
        self.original_filename = sanitize_original_filename(uploaded_file.name)
        self.file_size = uploaded_file.size


class ResourceAccessEvent(TimeStampedModel):
    """One download/read of a resource by a user - feeds school-level usage
    analytics. Aggregated only; never displayed per student anywhere."""

    class Kind(models.TextChoices):
        READ = "READ", "Read (inline)"
        DOWNLOAD = "DOWNLOAD", "Download"

    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="access_events"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resource_access_events"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["resource", "kind", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.resource.title} by {self.user}"


class BookChapter(TimeStampedModel):
    """A chapter of a BOOK resource."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="chapters")
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=255)
    start_page = models.PositiveIntegerField(null=True, blank=True)
    end_page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["resource", "number"]
        constraints = [
            models.UniqueConstraint(fields=["resource", "number"], name="unique_chapter_number_per_resource"),
        ]

    def __str__(self):
        return f"{self.number}. {self.title}"

    def clean(self):
        super().clean()
        if (
            self.start_page is not None
            and self.end_page is not None
            and self.start_page > self.end_page
        ):
            raise ValidationError({"end_page": "End page must not precede start page."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class BookSection(TimeStampedModel):
    """A section inside a chapter."""

    chapter = models.ForeignKey(BookChapter, on_delete=models.CASCADE, related_name="sections")
    number = models.DecimalField(max_digits=5, decimal_places=1)
    title = models.CharField(max_length=255)
    start_page = models.PositiveIntegerField(null=True, blank=True)
    end_page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["chapter", "number"]
        constraints = [
            models.UniqueConstraint(fields=["chapter", "number"], name="unique_section_number_per_chapter"),
        ]

    def __str__(self):
        return f"{self.number} {self.title}"

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.start_page is not None
            and self.end_page is not None
            and self.start_page > self.end_page
        ):
            errors["end_page"] = "End page must not precede start page."
        if self.chapter_id:
            chapter = self.chapter
            if chapter.start_page is not None and self.start_page is not None:
                if self.start_page < chapter.start_page:
                    errors["start_page"] = "Section starts before its chapter."
            if chapter.end_page is not None and self.end_page is not None:
                if self.end_page > chapter.end_page:
                    errors["end_page"] = "Section ends after its chapter."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)