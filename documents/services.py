"""Document processing services: extraction, chunking, orchestration.

Rules enforced here (AGENTS.md sections 7/11/13):

- The original file is never modified; results go to separate tables.
- Page boundaries are preserved so later phases can cite locations.
- Pages without an extractable text layer are reported honestly. A document
  whose pages are entirely un-extractable FAILS rather than pretending
  success ("OCR required" diagnostics). Tesseract-based OCR will slot into
  ``ocr_available``/``ocr_extract_page`` when deployed.
- Every run replaces prior extraction results (idempotent re-runs).
"""

import datetime
import io

from django.conf import settings
from django.db import transaction
from pypdf import PdfReader

from documents.models import (
    ChunkEmbedding,
    DocumentChunk,
    ExtractedPage,
    ProcessingJob,
    ProcessingLog,
)
from library.models import Resource


class PipelineError(Exception):
    """Raised when processing cannot proceed; message is admin-facing."""


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def log_event(resource, level, message):
    ProcessingLog.objects.create(resource=resource, level=level, message=message)


def set_processing_status(resource, status):
    """Update status without triggering model save()/clean() side effects."""
    type(resource).objects.filter(pk=resource.pk).update(processing_status=status)


def ocr_available():
    """OCR requires the Tesseract binary; not bundled in this phase."""
    return False


def _normalize(text):
    cleaned = (text or "").replace("\x00", "")
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned.strip()


@transaction.atomic
def extract_text(resource):
    """Extract per-page text. Returns dict of stats; raises PipelineError."""
    ExtractedPage.objects.filter(resource=resource).delete()

    data = resource.file.open("rb")
    try:
        reader = PdfReader(io.BytesIO(data.read()), strict=False)
        total_pages = len(reader.pages)
        max_pages = getattr(settings, "DOCUMENTS_MAX_PAGES", 2000)
        if total_pages > max_pages:
            raise PipelineError(
                f"Document has {total_pages} pages; limit is {max_pages}."
            )
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = _normalize(page.extract_text() or "")
                has_text = bool(text)
            except Exception as exc:  # noqa: BLE001 - single bad page must not kill run
                text, has_text = "", False
                log_event(
                    resource,
                    ProcessingLog.Level.WARNING,
                    f"Text extraction failed on page {index}: {exc}",
                )
            pages.append((index, text, has_text))
    finally:
        data.close()

    ExtractedPage.objects.bulk_create(
        ExtractedPage(resource=resource, page_number=n, text=t, has_text=h)
        for n, t, h in pages
    )

    missing = [n for n, _, has_text in pages if not has_text]
    if missing:
        sample = ", ".join(str(n) for n in missing[:10])
        suffix = "..." if len(missing) > 10 else ""
        if len(missing) == len(pages):
            raise PipelineError(
                "No extractable text on any page: the PDF appears to be "
                "scanned images. OCR is required but no OCR engine is "
                f"configured (pages: {sample}{suffix})."
            )
        log_event(
            resource,
            ProcessingLog.Level.WARNING,
            f"{len(missing)} page(s) have no text layer and require OCR "
            f"(pages: {sample}{suffix}). OCR is not configured in this phase.",
        )
    return {"total_pages": len(pages), "pages_without_text": len(missing)}


def _chapter_for_page(resource, page_number):
    candidates = [
        c for c in resource.chapters.all()
        if c.start_page is not None and c.start_page <= page_number
        and (c.end_page is None or page_number <= c.end_page)
    ]
    return min(candidates, key=lambda c: (c.end_page or c.start_page)) if candidates else None


def _section_for_page(chapter, page_number):
    if chapter is None:
        return None
    candidates = [
        s for s in chapter.sections.all()
        if s.start_page is not None and s.start_page <= page_number
        and (s.end_page is None or page_number <= s.end_page)
    ]
    return min(candidates, key=lambda s: (s.end_page or s.start_page)) if candidates else None


def _split_oversized(fragment, chunk_size):
    """Split a fragment larger than the chunk limit into word-boundary pieces."""
    if len(fragment) <= chunk_size:
        return [fragment]
    pieces, current = [], ""
    for word in fragment.split(" "):
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) > chunk_size and current:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


@transaction.atomic
def chunk_resource(resource):
    """Build chunks from extracted pages, anchored to pages and structure."""
    if not resource.extracted_pages.filter(has_text=True).exists():
        raise PipelineError("No extractable text found; run extraction first.")
    DocumentChunk.objects.filter(resource=resource).delete()

    chunk_size = getattr(settings, "DOCUMENTS_CHUNK_SIZE", 1200)
    overlap = getattr(settings, "DOCUMENTS_CHUNK_OVERLAP", 150)

    fragments = []  # (page_number, text)
    for page in resource.extracted_pages.order_by("page_number"):
        if not page.has_text:
            continue
        parts = [p.strip() for p in page.text.split("\n\n") if p.strip()] or [page.text]
        for part in parts:
            for piece in _split_oversized(part, chunk_size):
                fragments.append((page.page_number, piece))

    chunks = []
    buffer, buffer_pages = [], []

    def flush():
        if not buffer:
            return
        text = "\n\n".join(buffer).strip()
        if not text:
            return
        chunks.append((text, min(buffer_pages), max(buffer_pages)))

    for page_number, fragment in fragments:
        prospective = ("\n\n".join(buffer) + "\n\n" + fragment) if buffer else fragment
        if buffer and len(prospective) > chunk_size:
            flush()
            tail = "\n\n".join(buffer)[-overlap:]
            buffer, buffer_pages = [tail], [buffer_pages[-1]]
        buffer.append(fragment)
        buffer_pages.append(page_number)
    flush()

    DocumentChunk.objects.bulk_create(
        DocumentChunk(
            resource=resource,
            sequence=index,
            page_start=start,
            page_end=end,
            chapter=_chapter_for_page(resource, start),
            section=_section_for_page(_chapter_for_page(resource, start), start),
            text=text,
        )
        for index, (text, start, end) in enumerate(chunks, start=1)
    )
    return {"chunks": len(chunks)}


@transaction.atomic
def embed_resource_chunks(resource):
    """Embed chunks that lack a current-model vector; re-embed on model change.

    Embeddings are generated once per chunk unless the embedding model changes
    (AGENTS.md section 14). Returns stats about what was (re)embedded.
    """
    from ai.models import AIRequestLog  # noqa: F401 - imported for clarity in logs below
    from ai.providers import get_provider

    provider = get_provider()
    model_name = provider.model

    stale = ChunkEmbedding.objects.filter(chunk__resource=resource).exclude(
        model_name=model_name
    )
    if stale.exists():
        log_event(
            resource,
            ProcessingLog.Level.INFO,
            f"Embedding model changed to {model_name}; re-embedding "
            f"{stale.count()} stale vector(s).",
        )
        stale.delete()

    pending_chunks = list(
        DocumentChunk.objects.filter(resource=resource, embedding__isnull=True).order_by("sequence")
    )
    embedded_now = 0
    batch_size = 16
    for start in range(0, len(pending_chunks), batch_size):
        batch = pending_chunks[start : start + batch_size]
        try:
            vectors = provider.embed([chunk.text for chunk in batch])
        except Exception as exc:  # noqa: BLE001 - recorded as pipeline failure
            raise PipelineError(f"Embedding failed: {exc}") from exc
        for chunk, vector in zip(batch, vectors):
            ChunkEmbedding.objects.create(
                chunk=chunk,
                model_name=model_name,
                dimensions=len(vector),
                vector=list(vector),
            )
            embedded_now += 1

    return {
        "embedded": embedded_now,
        "skipped_existing": resource.chunks.count() - embedded_now,
        "model": model_name,
    }


@transaction.atomic
def execute_step(job):
    """Run one job's step. Raises PipelineError for expected failures."""
    resource = job.resource
    if job.step == ProcessingJob.Step.EXTRACT:
        if not resource.file:
            raise PipelineError("Resource has no attached file.")
        set_processing_status(resource, Resource.ProcessingStatus.VALIDATING)
        set_processing_status(resource, Resource.ProcessingStatus.EXTRACTING)
        stats = extract_text(resource)
        log_event(
            resource,
            ProcessingLog.Level.INFO,
            f"Extracted {stats['total_pages']} page(s); "
            f"{stats['pages_without_text']} without text layer.",
        )
    elif job.step == ProcessingJob.Step.CHUNK:
        if not resource.extracted_pages.exists():
            raise PipelineError("No extracted pages found; run extraction first.")
        set_processing_status(resource, Resource.ProcessingStatus.CHUNKING)
        stats = chunk_resource(resource)
        log_event(resource, ProcessingLog.Level.INFO, f"Created {stats['chunks']} chunk(s).")
        # READY is set by the EMBED step; dispatcher chains CHUNK -> EMBED.
    elif job.step == ProcessingJob.Step.EMBED:
        if not resource.chunks.exists():
            raise PipelineError("No chunks found; run chunking first.")
        set_processing_status(resource, Resource.ProcessingStatus.EMBEDDING)
        stats = embed_resource_chunks(resource)
        log_event(
            resource,
            ProcessingLog.Level.INFO,
            f"Embedded {stats['embedded']} chunk(s) with {stats['model']} "
            f"({stats['skipped_existing']} reused).",
        )
        set_processing_status(resource, Resource.ProcessingStatus.READY)
    else:
        raise PipelineError(f"Unknown processing step: {job.step}")
    return stats