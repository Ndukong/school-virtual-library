import io
import uuid
from unittest import mock

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from accounts.models import User
from documents.admin import DocumentChunkAdmin
from documents.dispatcher import claim_next_job, drain_queue, enqueue, process_job
from documents.models import (
    DocumentChunk,
    ExtractedPage,
    ProcessingJob,
    ProcessingLog,
)
from documents.services import PipelineError, extract_text, utcnow
from library.models import BookChapter, BookSection, Resource
from schools.models import School

PASSWORD = "ComplexPass123!"


def _escape(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(page_texts):
    """Assemble a small valid PDF with one content stream per page.

    Pages with empty strings produce no text operators, which simulates
    scanned pages without a text layer.
    """
    objects = {}
    count = len(page_texts)
    font_id = 3 + 2 * count
    kids = " ".join("%d 0 R" % (3 + 2 * i) for i in range(count))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, count)).encode()
    for i, text in enumerate(page_texts):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        objects[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> >> >>"
            % (content_id, font_id)
        ).encode()
        stream = ("BT /F1 12 Tf 72 720 Td (%s) Tj ET" % _escape(text)).encode("latin-1")
        objects[content_id] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += ("%d 0 obj\n" % number).encode() + objects[number] + b"\nendobj\n"
    xref_position = len(out)
    max_number = max(objects)
    out += ("xref\n0 %d\n" % (max_number + 1)).encode()
    out += b"0000000000 65535 f \n"
    for number in range(1, max_number + 1):
        out += ("%010d 00000 n \n" % offsets[number]).encode()
    out += (
        "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (max_number + 1, xref_position)
    ).encode()
    return bytes(out)


class DocumentsTestBase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")
        self.teacher_a = User.objects.create_user(
            "tcha", password=PASSWORD, role=User.Role.TEACHER, school=self.school_a
        )
        self.teacher_b = User.objects.create_user(
            "tchb", password=PASSWORD, role=User.Role.TEACHER, school=self.school_b
        )
        self.admin_a = User.objects.create_user(
            "adma", password=PASSWORD, role=User.Role.ADMIN, school=self.school_a, is_staff=True
        )

    def make_pdf_resource(self, pages=("Kinematics is the branch of mechanics.",
                                       "Dynamics deals with forces and motion."),
                          school=None, title="Physics Textbook", content=None):
        data = content if content is not None else build_pdf(list(pages))
        resource = Resource(
            school=school or self.school_a,
            title=title,
            uploaded_by=self.teacher_a if (school or self.school_a) == self.school_a else self.teacher_b,
            resource_type=Resource.ResourceType.BOOK,
        )
        resource.file.save("book.pdf", ContentFile(data), save=False)
        resource.original_filename = "book.pdf"
        resource.file_size = len(data)
        resource.save()
        return resource


class ExtractionTests(DocumentsTestBase):
    def test_extracts_pages_preserving_boundaries(self):
        resource = self.make_pdf_resource()
        stats = extract_text(resource)
        self.assertEqual(stats["total_pages"], 2)
        self.assertEqual(stats["pages_without_text"], 0)
        pages = list(resource.extracted_pages.order_by("page_number"))
        self.assertEqual([p.page_number for p in pages], [1, 2])
        self.assertIn("Kinematics", pages[0].text)
        self.assertIn("Dynamics", pages[1].text)
        self.assertTrue(all(p.has_text for p in pages))

    def test_extraction_is_idempotent(self):
        resource = self.make_pdf_resource()
        extract_text(resource)
        extract_text(resource)
        self.assertEqual(resource.extracted_pages.count(), 2)

    def test_scanned_pages_reported_not_faked(self):
        resource = self.make_pdf_resource(pages=("Visible intro text.", "", ""))
        stats = extract_text(resource)
        self.assertEqual(stats["pages_without_text"], 2)
        flagged = resource.extracted_pages.filter(has_text=False).count()
        self.assertEqual(flagged, 2)
        self.assertTrue(
            ProcessingLog.objects.filter(resource=resource, level=ProcessingLog.Level.WARNING).exists()
        )

    def test_fully_scanned_document_raises(self):
        resource = self.make_pdf_resource(pages=("", ""))
        with self.assertRaises(PipelineError) as ctx:
            extract_text(resource)
        self.assertIn("OCR is required", str(ctx.exception))


class ChunkingTests(DocumentsTestBase):
    def test_chunks_anchor_to_pages_and_structure(self):
        resource = self.make_pdf_resource()
        chapter = BookChapter.objects.create(
            resource=resource, number=1, title="Motion", start_page=1, end_page=2,
        )
        section = BookSection.objects.create(
            chapter=chapter, number=1.0, title="Kinematics", start_page=1, end_page=1,
        )
        extract_text(resource)
        stats = __import__("documents.services", fromlist=["chunk_resource"]).chunk_resource(resource)
        self.assertGreaterEqual(stats["chunks"], 1)
        first = resource.chunks.order_by("sequence").first()
        self.assertEqual(first.page_start, 1)
        self.assertEqual(first.chapter, chapter)
        self.assertEqual(first.section, section)

    def test_long_documents_split_into_multiple_chunks(self):
        filler = "The acceleration of a body depends on the net force acting upon it. " * 40
        pages = tuple([filler] * 3)
        resource = self.make_pdf_resource(pages=pages)
        extract_text(resource)
        from documents.services import chunk_resource

        chunk_resource(resource)
        chunks = list(resource.chunks.order_by("sequence"))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.text), 1200 + 150 + 200)
        sequences = [c.sequence for c in chunks]
        self.assertEqual(sequences, list(range(1, len(chunks) + 1)))

    def test_chunking_requires_extraction_first(self):
        resource = self.make_pdf_resource()
        from documents.services import chunk_resource

        with self.assertRaises(PipelineError):
            chunk_resource(resource)


class DispatcherTests(DocumentsTestBase):
    def test_enqueue_is_deduplicated_and_rearms(self):
        resource = self.make_pdf_resource()
        first = enqueue(resource, ProcessingJob.Step.EXTRACT)
        second = enqueue(resource, ProcessingJob.Step.EXTRACT)
        self.assertEqual(first, second)
        self.assertEqual(ProcessingJob.objects.count(), 1)

        first.status = ProcessingJob.Status.SUCCEEDED
        first.save()
        rearmed = enqueue(resource, ProcessingJob.Step.EXTRACT)
        self.assertEqual(rearmed.status, ProcessingJob.Status.PENDING)

    def test_claim_is_atomic_single_use(self):
        resource = self.make_pdf_resource()
        enqueue(resource, ProcessingJob.Step.EXTRACT)
        first = claim_next_job()
        self.assertIsNotNone(first)
        self.assertEqual(first.status, ProcessingJob.Status.RUNNING)
        self.assertIsNone(claim_next_job())

    def test_claim_empty_queue_returns_none(self):
        self.assertIsNone(claim_next_job())

    def test_retry_until_max_attempts(self):
        resource = self.make_pdf_resource(content=b"%PDF-1.4 broken but signed")
        with override_settings(DOCUMENTS_MAX_ATTEMPTS=1):
            job = enqueue(resource, ProcessingJob.Step.EXTRACT)
            process_job(job)
        self.assertEqual(job.status, ProcessingJob.Status.FAILED)
        self.assertIn("Unexpected error", job.last_error)
        self.assertEqual(job.attempts, 1)
        resource.refresh_from_db()
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.FAILED)
        self.assertTrue(
            ProcessingLog.objects.filter(resource=resource, level=ProcessingLog.Level.ERROR).exists()
        )

    def test_transient_failure_then_success(self):
        import documents.services

        resource = self.make_pdf_resource(pages=("Some physics text.",))
        real_extract = documents.services.extract_text
        calls = {"count": 0}

        def flaky_extract(target_resource):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient")
            return real_extract(target_resource)

        job = enqueue(resource, ProcessingJob.Step.EXTRACT)
        with mock.patch("documents.services.extract_text", side_effect=flaky_extract):
            process_job(job)  # attempt 1 fails -> PENDING for retry
            self.assertEqual(job.status, ProcessingJob.Status.PENDING)
            job = claim_next_job()
            process_job(job)  # attempt 2 runs the real extraction
        self.assertEqual(job.status, ProcessingJob.Status.SUCCEEDED)
        resource.refresh_from_db()
        self.assertEqual(resource.extracted_pages.count(), 1)

    def test_corrupt_file_fails_without_touching_original(self):
        original = b"%PDF-1.4\ntruncated nonsense with no xref table"
        resource = self.make_pdf_resource(content=original)
        with override_settings(DOCUMENTS_MAX_ATTEMPTS=1):
            job = enqueue(resource, ProcessingJob.Step.EXTRACT)
            process_job(job)
        self.assertEqual(job.status, ProcessingJob.Status.FAILED)
        resource.file.open("rb")
        self.assertEqual(resource.file.read(), original)
        resource.file.close()


@override_settings(DOCUMENTS_INLINE_PROCESSING=True)
class InlinePipelineIntegrationTests(DocumentsTestBase):
    def test_full_upload_to_ready_pipeline(self):
        client = Client()
        client.force_login(self.teacher_a)
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.urls import reverse

        pdf = build_pdf(["Chapter one text about motion.", "Chapter two text about forces."])
        response = client.post(
            reverse("library-upload"),
            {
                "title": "Integrated Physics",
                "resource_type": Resource.ResourceType.BOOK,
                "licensing_status": Resource.LicensingStatus.OWNED,
                "access_policy": Resource.AccessPolicy.SCHOOL,
                "file": SimpleUploadedFile("integrated.pdf", pdf),
            },
        )
        resource = Resource.objects.get(title="Integrated Physics")
        self.assertRedirects(response, resource.get_absolute_url())
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.READY)
        self.assertEqual(resource.extracted_pages.count(), 2)
        self.assertGreaterEqual(resource.chunks.count(), 1)
        self.assertTrue(
            resource.processing_jobs.filter(status=ProcessingJob.Status.SUCCEEDED).count() >= 2
        )
        self.assertFalse(
            resource.processing_logs.filter(level=ProcessingLog.Level.ERROR).exists()
        )

    def test_scanned_upload_fails_honestly(self):
        client = Client()
        client.force_login(self.teacher_a)
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.urls import reverse

        pdf = build_pdf(["", ""])
        client.post(
            reverse("library-upload"),
            {
                "title": "Scanned Book",
                "resource_type": Resource.ResourceType.BOOK,
                "licensing_status": Resource.LicensingStatus.OWNED,
                "access_policy": Resource.AccessPolicy.SCHOOL,
                "file": SimpleUploadedFile("scanned.pdf", pdf),
            },
        )
        resource = Resource.objects.get(title="Scanned Book")
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.FAILED)
        self.assertTrue(
            resource.processing_logs.filter(
                level=ProcessingLog.Level.ERROR, message__icontains="OCR"
            ).exists()
        )


class WorkerCommandTests(DocumentsTestBase):
    def test_drain_processes_pending_jobs_in_order(self):
        from documents.models import ChunkEmbedding

        resource = self.make_pdf_resource()
        enqueue(resource, ProcessingJob.Step.EXTRACT)
        enqueue(resource, ProcessingJob.Step.CHUNK)
        with override_settings(DOCUMENTS_INLINE_PROCESSING=False):
            processed = drain_queue()
        # EXTRACT + CHUNK + chained EMBED.
        self.assertEqual(processed, 3)
        resource.refresh_from_db()
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.READY)
        self.assertEqual(
            ProcessingJob.objects.filter(status=ProcessingJob.Status.SUCCEEDED).count(), 3
        )
        self.assertTrue(ChunkEmbedding.objects.filter(chunk__resource=resource).exists())

    def test_management_command_once(self):
        resource = self.make_pdf_resource()
        enqueue(resource, ProcessingJob.Step.EXTRACT)
        enqueue(resource, ProcessingJob.Step.CHUNK)
        call_command("process_documents")
        resource.refresh_from_db()
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.READY)

    def test_management_command_resource_id_reruns_pipeline(self):
        resource = self.make_pdf_resource()
        extract_text(resource)
        call_command("process_documents", resource_id=str(resource.public_id))
        resource.refresh_from_db()
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.READY)
        self.assertGreaterEqual(resource.chunks.count(), 1)


class AdminScopingTests(DocumentsTestBase):
    def test_chunk_admin_scoped_to_admins_school(self):
        from django.contrib.admin import site as admin_site
        from django.test import RequestFactory

        mine = self.make_pdf_resource(title="Mine")
        extract_text(mine)
        from documents.services import chunk_resource

        chunk_resource(mine)
        foreign = self.make_pdf_resource(title="Foreign", school=self.school_b)
        extract_text(foreign)
        chunk_resource(foreign)

        request = RequestFactory().get("/admin/")
        request.user = self.admin_a
        queryset = DocumentChunkAdmin(DocumentChunk, admin_site).get_queryset(request)
        resources = set(queryset.values_list("resource__title", flat=True))
        self.assertEqual(resources, {"Mine"})
