import atexit
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from classes.models import SchoolClass
from library.admin import ResourceAdmin
from library.models import BookChapter, BookSection, Resource
from library.services import user_can_read_resource, visible_resources
from schools.models import School
from subjects.models import Subject

PASSWORD = "ComplexPass123!"

MEDIA_TMP = tempfile.mkdtemp()
atexit.register(lambda: shutil.rmtree(MEDIA_TMP, ignore_errors=True))


def pdf_bytes(content=b"%PDF-1.4 minimal test document"):
    return b"%PDF-1.4\n" + content


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class LibraryTestBase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")
        self.physics_a = Subject.objects.create(school=self.school_a, name="Physics")
        self.form1_a = SchoolClass.objects.create(school=self.school_a, name="Form 1")
        self.teacher_a = User.objects.create_user(
            "tcha", password=PASSWORD, role=User.Role.TEACHER, school=self.school_a
        )
        self.teacher_b = User.objects.create_user(
            "tchb", password=PASSWORD, role=User.Role.TEACHER, school=self.school_b
        )
        self.student_a = User.objects.create_user(
            "stua", password=PASSWORD, role=User.Role.STUDENT, school=self.school_a
        )
        self.admin_a = User.objects.create_user(
            "adma", password=PASSWORD, role=User.Role.ADMIN,
            school=self.school_a, is_staff=True,
        )
        self.superuser = User.objects.create_user("root", password=PASSWORD, is_superuser=True)
        self.student_b = User.objects.create_user(
            "stub", password=PASSWORD, role=User.Role.STUDENT, school=self.school_b
        )

    def make_resource(self, title="Physics Textbook", school=None, uploader=None,
                      access_policy=Resource.AccessPolicy.SCHOOL,
                      resource_type=Resource.ResourceType.BOOK, is_active=True,
                      with_file=True, licensing_status=Resource.LicensingStatus.OWNED):
        school = school or self.school_a
        uploader = uploader or (
            self.teacher_a if school == self.school_a else self.teacher_b
        )
        resource = Resource(
            school=school,
            title=title,
            uploaded_by=uploader,
            resource_type=resource_type,
            access_policy=access_policy,
            is_active=is_active,
            licensing_status=licensing_status,
        )
        if with_file:
            resource.file.save(f"{title.replace(' ', '_')}.pdf", ContentFile(pdf_bytes()), save=False)
            resource.original_filename = f"{title}.pdf"
            resource.file_size = len(pdf_bytes())
        resource.save()
        return resource


class ResourceModelTests(LibraryTestBase):
    def test_str_and_defaults(self):
        resource = self.make_resource()
        self.assertEqual(str(resource), "Physics Textbook")
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.UPLOADED)
        self.assertEqual(resource.language, "en")

    def test_book_requires_file(self):
        resource = Resource(
            school=self.school_a, title="No File Book",
            uploaded_by=self.teacher_a, resource_type=Resource.ResourceType.BOOK,
        )
        with self.assertRaises(ValidationError) as ctx:
            resource.full_clean()
        self.assertIn("file", ctx.exception.message_dict)

    def test_non_book_without_file_allowed(self):
        resource = Resource(
            school=self.school_a, title="Loose notes",
            uploaded_by=self.teacher_a, resource_type=Resource.ResourceType.NOTES,
        )
        resource.full_clean()

    def test_subject_from_other_school_rejected(self):
        foreign_subject = Subject.objects.create(school=self.school_b, name="Physics")
        resource = Resource(
            school=self.school_a, title="X", uploaded_by=self.teacher_a,
            subject=foreign_subject, resource_type=Resource.ResourceType.NOTES,
        )
        with self.assertRaises(ValidationError) as ctx:
            resource.full_clean()
        self.assertIn("subject", ctx.exception.message_dict)

    def test_class_from_other_school_rejected(self):
        foreign_class = SchoolClass.objects.create(school=self.school_b, name="Form 1")
        resource = Resource(
            school=self.school_a, title="X", uploaded_by=self.teacher_a,
            school_class=foreign_class, resource_type=Resource.ResourceType.NOTES,
        )
        with self.assertRaises(ValidationError) as ctx:
            resource.full_clean()
        self.assertIn("school_class", ctx.exception.message_dict)

    def test_publication_year_bounds(self):
        base = dict(school=self.school_a, uploaded_by=self.teacher_a,
                    resource_type=Resource.ResourceType.NOTES)
        with self.assertRaises(ValidationError):
            Resource(title="old", publication_year=1000, **base).full_clean()
        with self.assertRaises(ValidationError):
            Resource(title="future", publication_year=3000, **base).full_clean()

    def test_replacing_file_resets_processing_status(self):
        resource = self.make_resource()
        resource.processing_status = Resource.ProcessingStatus.READY
        resource.save()
        resource.file.save("replacement.pdf", ContentFile(pdf_bytes(b"%PDF-1.4 v2")), save=False)
        resource.save()
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.UPLOADED)


class ChapterSectionTests(LibraryTestBase):
    def test_chapter_pages_order_enforced(self):
        resource = self.make_resource()
        chapter = BookChapter(resource=resource, number=1, title="Motion",
                              start_page=10, end_page=5)
        with self.assertRaises(ValidationError):
            chapter.save()

    def test_chapter_number_unique_per_resource(self):
        resource = self.make_resource()
        BookChapter.objects.create(resource=resource, number=1, title="Motion")
        duplicate = BookChapter(resource=resource, number=1, title="Again")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_section_must_fit_inside_chapter(self):
        resource = self.make_resource()
        chapter = BookChapter.objects.create(
            resource=resource, number=2, title="Forces", start_page=20, end_page=40,
        )
        before = BookSection(chapter=chapter, number=1, title="Intro", start_page=15, end_page=25)
        with self.assertRaises(ValidationError):
            before.full_clean()
        inside = BookSection(chapter=chapter, number=1, title="Intro", start_page=21, end_page=30)
        inside.full_clean()
class AccessRuleTests(LibraryTestBase):
    def test_access_matrix(self):
        school_resource = self.make_resource("Open Book")
        teachers_only = self.make_resource(
            "Staff Papers", access_policy=Resource.AccessPolicy.TEACHERS_ONLY,
        )
        inactive = self.make_resource("Withdrawn", is_active=False)
        foreign = self.make_resource("Other School Book", school=self.school_b)

        self.assertTrue(user_can_read_resource(self.superuser, foreign))
        self.assertTrue(user_can_read_resource(self.teacher_a, teachers_only))
        self.assertTrue(user_can_read_resource(self.admin_a, inactive))
        self.assertTrue(user_can_read_resource(self.student_a, school_resource))

        self.assertFalse(user_can_read_resource(self.student_a, teachers_only))
        self.assertFalse(user_can_read_resource(self.student_a, inactive))
        self.assertFalse(user_can_read_resource(self.student_b, school_resource))
        self.assertFalse(user_can_read_resource(self.teacher_a, foreign))

    def test_visible_resources_scoping(self):
        open_book = self.make_resource("Open Book")
        self.make_resource(
            "Staff Papers", access_policy=Resource.AccessPolicy.TEACHERS_ONLY,
        )

        student_ids = set(visible_resources(self.student_a).values_list("pk", flat=True))
        self.assertEqual(student_ids, {open_book.pk})

        teacher_ids = visible_resources(self.teacher_a)
        self.assertEqual(teacher_ids.count(), 2)

    def test_anonymous_sees_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(visible_resources(AnonymousUser()).count(), 0)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class LibraryViewAccessTests(LibraryTestBase):
    def setUp(self):
        super().setUp()
        self.open_book = self.make_resource(
            "Open Book",
            licensing_status=Resource.LicensingStatus.OPEN_ACCESS,
        )
        self.teachers_only = self.make_resource(
            "Staff Papers", access_policy=Resource.AccessPolicy.TEACHERS_ONLY,
        )
        self.foreign = self.make_resource("Other School Book", school=self.school_b)

    def test_anonymous_redirected_to_login(self):
        response = Client().get(reverse("library-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_student_list_hides_teachers_only_and_foreign(self):
        self.client.force_login(self.student_a)
        response = self.client.get(reverse("library-list"))
        self.assertContains(response, "Open Book")
        self.assertNotContains(response, "Staff Papers")
        self.assertNotContains(response, "Other School Book")

    def test_student_detail_denied_for_teachers_only(self):
        self.client.force_login(self.student_a)
        url = reverse("library-detail", args=[self.teachers_only.public_id])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_student_detail_allowed_for_school_policy(self):
        self.client.force_login(self.student_a)
        url = reverse("library-detail", args=[self.open_book.public_id])
        self.assertContains(self.client.get(url), "Open Book")

    def test_cross_school_detail_denied(self):
        self.client.force_login(self.student_a)
        url = reverse("library-detail", args=[self.foreign.public_id])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_inactive_hidden_from_students_visible_to_admin(self):
        withdrawn = self.make_resource("Withdrawn", is_active=False)
        self.client.force_login(self.student_a)
        url = reverse("library-detail", args=[withdrawn.public_id])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin_a)
        self.assertContains(self.client.get(url), "Withdrawn")

    def test_download_enforces_same_rules(self):
        self.client.force_login(self.student_a)
        denied = reverse("library-download", args=[self.teachers_only.public_id])
        self.assertEqual(self.client.get(denied).status_code, 404)
        allowed = reverse("library-download", args=[self.open_book.public_id])
        response = self.client.get(allowed)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/pdf"))
        self.assertIn("attachment", response["Content-Disposition"])

    def test_read_view_streams_inline(self):
        self.client.force_login(self.student_a)
        url = reverse("library-read", args=[self.open_book.public_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("inline", response["Content-Disposition"])

    def test_list_filters_by_type_and_query(self):
        paper = self.make_resource("Algebra Paper", resource_type=Resource.ResourceType.PAST_PAPER)
        self.client.force_login(self.student_a)
        response = self.client.get(reverse("library-list"), {"type": "PAST_PAPER"})
        self.assertContains(response, "Algebra Paper")
        self.assertNotContains(response, "Open Book")
        response = self.client.get(reverse("library-list"), {"q": "algebra"})
        self.assertContains(response, "Algebra Paper")
        self.assertNotContains(response, "Open Book")

    def test_pagination_out_of_range_is_safe(self):
        self.make_resource("Another Book")
        self.client.force_login(self.student_a)
        response = self.client.get(reverse("library-list"), {"page": "9999"})
        self.assertEqual(response.status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class UploadSecurityTests(LibraryTestBase):
    def _upload_url(self):
        return reverse("library-upload")

    def _post_resource(self, client, filename="textbook.pdf", content=None, **extra):
        payload = {
            "title": "Uploaded Textbook",
            "resource_type": Resource.ResourceType.BOOK,
            "licensing_status": Resource.LicensingStatus.OWNED,
            "access_policy": Resource.AccessPolicy.SCHOOL,
            "file": SimpleUploadedFile(filename, content or pdf_bytes()),
        }
        payload.update(extra)
        return client.post(self._upload_url(), payload)

    def test_student_cannot_upload(self):
        self.client.force_login(self.student_a)
        self.assertEqual(self.client.get(self._upload_url()).status_code, 403)

    def test_teacher_uploads_successfully(self):
        self.client.force_login(self.teacher_a)
        response = self._post_resource(self.client)
        resource = Resource.objects.get(title="Uploaded Textbook")
        self.assertRedirects(response, resource.get_absolute_url())
        self.assertEqual(resource.school, self.school_a)
        self.assertEqual(resource.uploaded_by, self.teacher_a)
        self.assertEqual(resource.original_filename, "textbook.pdf")
        self.assertEqual(resource.processing_status, Resource.ProcessingStatus.UPLOADED)
        self.assertTrue(resource.file.storage.exists(resource.file.name))

    def test_subject_choice_limited_to_own_school(self):
        foreign_subject = Subject.objects.create(school=self.school_b, name="Physics")
        self.client.force_login(self.teacher_a)
        response = self._post_resource(self.client, subject=foreign_subject.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Resource.objects.filter(title="Uploaded Textbook").exists())

    def test_rejects_non_pdf_extension(self):
        self.client.force_login(self.teacher_a)
        response = self._post_resource(self.client, filename="notes.exe")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Resource.objects.filter(title="Uploaded Textbook").exists())

    def test_rejects_disguised_non_pdf_content(self):
        self.client.force_login(self.teacher_a)
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        response = self._post_resource(self.client, filename="fake.pdf", content=png)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Resource.objects.filter(title="Uploaded Textbook").exists())

    def test_rejects_oversized_file(self):
        from django.test import override_settings as override

        self.client.force_login(self.teacher_a)
        with override(LIBRARY_MAX_UPLOAD_MB=0):
            response = self._post_resource(self.client)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Resource.objects.filter(title="Uploaded Textbook").exists())

    def test_path_traversal_filename_sanitized(self):
        self.client.force_login(self.teacher_a)
        self._post_resource(self.client, filename="..\\..\\evil.pdf")
        resource = Resource.objects.get(title="Uploaded Textbook")
        self.assertEqual(resource.original_filename, "evil.pdf")
        self.assertNotIn("..", resource.file.name)

    def test_superuser_selects_school(self):
        self.client.force_login(self.superuser)
        response = self._post_resource(self.client, school=self.school_a.pk)
        resource = Resource.objects.get(title="Uploaded Textbook")
        self.assertRedirects(response, resource.get_absolute_url())
        self.assertEqual(resource.school, self.school_a)


class AdminChainScopingTests(LibraryTestBase):
    def test_resource_admin_queryset_scoped_to_school(self):
        from django.contrib.admin import site as admin_site
        from django.test import RequestFactory

        self.make_resource("Mine A")
        self.make_resource("Other B", school=self.school_b)
        request = RequestFactory().get("/admin/")
        request.user = self.admin_a
        queryset = ResourceAdmin(Resource, admin_site).get_queryset(request)
        titles = set(queryset.values_list("title", flat=True))
        self.assertEqual(titles, {"Mine A"})

class ResourceDetailPageTests(LibraryTestBase):
    """Every Resource.ResourceType detail page must render (AGENTS section 8).
    Regression for the class-level Resource.chapters.none() crash."""

    def test_every_resource_type_detail_page_renders(self):
        for resource_type in Resource.ResourceType.values:
            with self.subTest(resource_type=resource_type):
                resource = self.make_resource(
                    title=f"{resource_type} doc", resource_type=resource_type,
                )
                self.client.force_login(self.student_a)
                response = self.client.get(
                    reverse("library-detail", args=[resource.public_id])
                )
                self.assertEqual(response.status_code, 200)

class FileServingHardeningTests(LibraryTestBase):
    """WP3: file endpoints send hardening headers and proper HTTP semantics."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.student_a)

    def _download(self, resource=None):
        resource = resource or self.make_resource()
        return self.client.get(reverse("library-download", args=[resource.public_id]))

    def test_headers_present_on_download(self):
        response = self._download()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_read_view_is_sandboxed_csp(self):
        resource = self.make_resource(
            licensing_status=Resource.LicensingStatus.OPEN_ACCESS,
        )
        response = self.client.get(reverse("library-read", args=[resource.public_id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Security-Policy"], "default-src 'none'; sandbox")

    def test_range_request_returns_206_partial(self):
        resource = self.make_resource()
        response = self.client.get(
            reverse("library-download", args=[resource.public_id]),
            HTTP_RANGE="bytes=0-9",
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], f"bytes 0-9/{resource.file_size}")
        self.assertEqual(len(b"".join(response.streaming_content)), 10)
        self.assertEqual(response["Accept-Ranges"], "bytes")

    def test_etag_and_last_modified_present(self):
        response = self._download()
        self.assertTrue(response["ETag"].startswith('"'))
        self.assertIn("GMT", response["Last-Modified"])

    def test_invalid_range_returns_416(self):
        resource = self.make_resource()
        response = self.client.get(
            reverse("library-download", args=[resource.public_id]),
            HTTP_RANGE="bytes=abc",
        )
        self.assertEqual(response.status_code, 416)
        self.assertIn("bytes */", response["Content-Range"])

    def test_xaccel_mode_does_not_stream(self):
        with override_settings(LIBRARY_XACCEL_ENABLED=True):
            resource = self.make_resource()
            response = self.client.get(reverse("library-download", args=[resource.public_id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Accel-Redirect"].startswith("/internal/"))

    def test_watermarked_read_for_licensed_owned_only(self):
        licensed = self.make_resource(licensing_status=Resource.LicensingStatus.LICENSED)
        open_access = self.make_resource(
            title="Open book",
            licensing_status=Resource.LicensingStatus.OPEN_ACCESS,
        )
        licensed_page = self.client.get(reverse("library-read", args=[licensed.public_id]))
        self.assertEqual(licensed_page.status_code, 200)
        self.assertContains(licensed_page, "Watermarked for")
        self.assertContains(licensed_page, reverse("library-stream", args=[licensed.public_id]))
        raw = self.client.get(reverse("library-read", args=[open_access.public_id]))
        self.assertTrue(raw["Content-Type"].startswith("application/pdf"))

    @override_settings(LIBRARY_DOWNLOAD_PER_MINUTE=2)
    def test_download_burst_throttled(self):
        resource = self.make_resource()
        url = reverse("library-download", args=[resource.public_id])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 429)

    @override_settings(LIBRARY_DOWNLOAD_DAILY_CAP=2, LIBRARY_DOWNLOAD_PER_MINUTE=100)
    def test_download_daily_cap_enforced(self):
        resource = self.make_resource()
        url = reverse("library-download", args=[resource.public_id])
        for _ in range(2):
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 429)
@override_settings(SCHOOL_STORAGE_QUOTA_MB=1)
class StorageQuotaTests(LibraryTestBase):
    def test_quota_rejects_upload_when_school_is_full(self):
        # School already uses the full 1MB quota.
        Resource.objects.create(
            school=self.school_a, title="Filler", uploaded_by=self.teacher_a,
            resource_type=Resource.ResourceType.NOTES, file_size=1024 * 1024,
        )
        self.client.force_login(self.teacher_a)
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(
            reverse("library-upload"),
            {
                "title": "Quota Blocked",
                "resource_type": Resource.ResourceType.NOTES,
                "licensing_status": Resource.LicensingStatus.OWNED,
                "access_policy": Resource.AccessPolicy.SCHOOL,
                "file": SimpleUploadedFile("quota.pdf", b"%PDF-1.4"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School storage quota reached")
        self.assertFalse(Resource.objects.filter(title="Quota Blocked").exists())

    def test_normal_upload_passes_quota(self):
        self.client.force_login(self.teacher_a)
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(
            reverse("library-upload"),
            {
                "title": "Quota Fine",
                "resource_type": Resource.ResourceType.NOTES,
                "licensing_status": Resource.LicensingStatus.OWNED,
                "access_policy": Resource.AccessPolicy.SCHOOL,
                "file": SimpleUploadedFile("ok.pdf", b"%PDF-1.4"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Resource.objects.filter(title="Quota Fine").exists())
