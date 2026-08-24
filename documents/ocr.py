"""OCR service (WP4).

The real engine shells out to ocrmypdf, which needs Tesseract + Ghostscript
for the configured languages (default eng,fra). When the binaries are missing
the pipeline degrades gracefully: blank pages are flagged ``needs_ocr`` and
processing carries on - text is never fabricated. Low-confidence output marks
the resource for teacher review. Tests inject a deterministic fake engine
(``DOCUMENTS_OCR_FAKE_ENGINE``) so the whole pipeline is exercised without
system OCR.

Resumable: only pages flagged ``needs_ocr`` with no ``ocr_at`` are retried.
"""

import shutil
import time

from django.conf import settings
from django.utils import timezone

from documents.models import ExtractedPage, ProcessingLog
from library.models import Resource


class OcrUnavailable(Exception):
    """Raised when the real OCR engine's system dependencies are missing."""


def _log_event(resource, level, message):
    ProcessingLog.objects.create(resource=resource, level=level, message=message)


def _set_status(resource, status):
    Resource.objects.filter(pk=resource.pk).update(processing_status=status)


def configured_languages():
    raw = getattr(settings, "DOCUMENTS_OCR_LANGUAGES", "eng,fra")
    return [lang.strip() for lang in raw.split(",") if lang.strip()] or ["eng"]


def tesseract_available():
    return shutil.which("tesseract") is not None


def get_ocr_engine():
    if getattr(settings, "DOCUMENTS_OCR_FAKE_ENGINE", False):
        return FakeOcrEngine()
    if not tesseract_available():
        raise OcrUnavailable("tesseract binary not found on PATH")
    return OcrmypdfEngine()


class OcrmypdfEngine:
    """Real OCR via ocrmypdf's Python API (needs tesseract + ghostscript)."""

    def languages(self):
        return configured_languages()

    def ocr_page(self, pdf_path, page_number, languages):
        """OCR one 1-based page; returns (text, confidence|None)."""
        import tempfile
        from pathlib import Path

        import ocrmypdf
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ocr.pdf"
            ocrmypdf.ocr(
                pdf_path,
                output,
                language=languages,
                pages=[page_number],
                deskew=True,
                optimize=1,
                force_ocr=True,
            )
            page = PdfReader(str(output)).pages[0]
        text = (page.extract_text() or "").strip()
        return text, None


class FakeOcrEngine:
    """Deterministic test engine driven by settings knobs."""

    def languages(self):
        return configured_languages()

    def ocr_page(self, pdf_path, page_number, languages):
        if getattr(settings, "DOCUMENTS_OCR_FAKE_SLEEP", 0) > 0:
            import time as _time

            _time.sleep(_get_sleep())
        confidence = _get_confidence()
        if getattr(settings, "DOCUMENTS_OCR_FAKE_EMPTY", False):
            return "", float(confidence)
        return f"OCR page {page_number} text", float(confidence)


def _get_confidence():
    return float(getattr(settings, "DOCUMENTS_OCR_FAKE_CONFIDENCE", 0.9))


def _get_sleep():
    return float(getattr(settings, "DOCUMENTS_OCR_FAKE_SLEEP", 0))


def _flag_blank_pages(resource, message):
    pages = resource.extracted_pages.filter(has_text=False)
    pages.update(needs_ocr=True)
    _log_event(resource, ProcessingLog.Level.WARNING, message)
    return pages.count()


def run_ocr_for_resource(resource):
    """OCR the resource's blank pages; never fabricates text.

    Returns {"status": "ok"|"unavailable"|"no-file", ...}.
    """
    try:
        engine = get_ocr_engine()
    except OcrUnavailable as exc:
        count = _flag_blank_pages(
            resource,
            f"OCR engine unavailable ({exc}); {resource.extracted_pages.filter(has_text=False).count()} "
            "blank page(s) flagged for OCR.",
        )
        _mark_review(resource)
        return {"status": "unavailable", "flagged": count}

    if not resource.file:
        return {"status": "no-file"}

    try:
        pdf_path = resource.file.path
    except NotImplementedError:
        return {"status": "no-file"}

    languages = engine.languages()
    pending = resource.extracted_pages.filter(
        has_text=False, needs_ocr=True, ocr_at__isnull=True
    ).order_by("page_number")
    if not pending.exists():
        # First pass: mark the blank pages as OCR candidates.
        resource.extracted_pages.filter(has_text=False).update(needs_ocr=True)
        pending = resource.extracted_pages.filter(
            has_text=False, needs_ocr=True, ocr_at__isnull=True
        ).order_by("page_number")

    cap = getattr(settings, "DOCUMENTS_OCR_MAX_PAGES", 500)
    timeout = getattr(settings, "DOCUMENTS_OCR_TIMEOUT_SECONDS", 300)
    pending = list(pending[:cap])
    if not pending:
        return {"status": "ok", "ocr_pages": 0, "low_confidence": 0}

    _set_status(resource, Resource.ProcessingStatus.OCR_PROCESSING)
    start = time.monotonic()
    total = len(pending)
    processed = 0
    low_confidence = []
    for position, page in enumerate(pending, start=1):
        if time.monotonic() - start > timeout:
            remaining = len(pending) - position
            _log_event(
                resource,
                ProcessingLog.Level.WARNING,
                f"OCR timed out after {timeout}s; {remaining} page(s) "
                "remain flagged for a later run.",
            )
            ExtractedPage.objects.filter(
                resource=resource, page_number__gte=page.page_number
            ).update(needs_ocr=True)
            break
        try:
            text, confidence = engine.ocr_page(pdf_path, page.page_number, languages)
        except Exception as exc:  # noqa: BLE001 - per-page failures are contained
            _log_event(
                resource,
                ProcessingLog.Level.WARNING,
                f"OCR failed on page {page.page_number}: {exc}",
            )
            ExtractedPage.objects.filter(pk=page.pk).update(needs_ocr=True)
            continue
        page.text = text
        page.has_text = bool(text.strip())
        page.ocr_confidence = confidence
        page.ocr_at = timezone.now()
        page.needs_ocr = not page.has_text  # stays flagged when nothing read
        page.save(update_fields=[
            "text", "has_text", "ocr_confidence", "ocr_at", "needs_ocr", "updated_at",
        ])
        processed += 1
        if page.has_text and confidence is not None and confidence < 0.4:
            low_confidence.append(page.page_number)
        _log_event(
            resource,
            ProcessingLog.Level.INFO,
            f"OCR page {page.page_number}/{total} ({','.join(languages)}) "
            f"confidence={confidence if confidence is not None else 'n/a'}.",
        )

    if low_confidence:
        _log_event(
            resource,
            ProcessingLog.Level.WARNING,
            "Low-confidence OCR on pages: " + ", ".join(str(n) for n in low_confidence),
        )
    _mark_review(resource)
    return {"status": "ok", "ocr_pages": processed, "low_confidence": len(low_confidence)}


def _mark_review(resource):
    needs_review = (
        resource.extracted_pages.filter(needs_ocr=True).exists()
        or resource.extracted_pages.filter(
            ocr_confidence__lt=0.4, ocr_confidence__isnull=False
        ).exists()
    )
    Resource.objects.filter(pk=resource.pk).update(needs_teacher_review=needs_review)