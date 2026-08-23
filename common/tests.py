"""Phase 0 configuration smoke tests plus Phase 1 admin scoping tests."""

from django.apps import apps
from django.conf import settings
from django.contrib.admin import site as default_admin_site
from django.test import RequestFactory, SimpleTestCase, TestCase

from accounts.models import User
from classes.admin import SchoolClassAdmin
from classes.models import SchoolClass
from schools.models import School


class ProjectConfigurationTests(SimpleTestCase):
    def test_secret_key_is_configured(self):
        self.assertIsInstance(settings.SECRET_KEY, str)
        self.assertGreaterEqual(len(settings.SECRET_KEY.strip()), 32)

    def test_debug_is_boolean(self):
        self.assertIsInstance(settings.DEBUG, bool)

    def test_common_app_is_installed(self):
        self.assertTrue(apps.is_installed("common"))

    def test_default_database_is_sqlite(self):
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3")

    def test_urlconf_imports(self):
        from django.urls import get_resolver

        resolver = get_resolver()
        self.assertIsNotNone(resolver.url_patterns)

    def test_media_and_static_roots_configured(self):
        self.assertTrue(settings.STATIC_ROOT)
        self.assertTrue(settings.MEDIA_ROOT)


class SchoolScopedAdminTests(TestCase):
    """Non-superuser admins must only see and manage their own school."""

    def setUp(self):
        self.school_a = School.objects.create(name="Alpha Academy")
        self.school_b = School.objects.create(name="Beta High")
        self.class_a = SchoolClass.objects.create(school=self.school_a, name="Form 1")
        self.class_b = SchoolClass.objects.create(school=self.school_b, name="Form 1")
        self.school_admin = User.objects.create_user(
            username="sa",
            password="ComplexPass123!",
            role=User.Role.ADMIN,
            school=self.school_a,
            is_staff=True,
        )
        self.superuser = User.objects.create_user(
            username="root", password="ComplexPass123!", is_superuser=True
        )
        self.factory = RequestFactory()

    def _request_for(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def _model_admin(self):
        return SchoolClassAdmin(SchoolClass, default_admin_site)

    def test_school_admin_sees_only_own_school(self):
        queryset = self._model_admin().get_queryset(self._request_for(self.school_admin))
        ids = set(queryset.values_list("pk", flat=True))
        self.assertEqual(ids, {self.class_a.pk})

    def test_admin_without_school_sees_nothing(self):
        orphan = User.objects.create_user(
            username="orphan",
            password="ComplexPass123!",
            role=User.Role.ADMIN,
            school=None,
            is_staff=True,
        )
        queryset = self._model_admin().get_queryset(self._request_for(orphan))
        self.assertFalse(queryset.exists())

    def test_superuser_sees_all(self):
        queryset = self._model_admin().get_queryset(self._request_for(self.superuser))
        self.assertEqual(queryset.count(), 2)

    def test_save_model_forces_admins_own_school(self):
        obj = SchoolClass(school=self.school_b, name="Form 2")
        self._model_admin().save_model(
            self._request_for(self.school_admin), obj, form=None, change=False
        )
        obj.refresh_from_db()
        self.assertEqual(obj.school, self.school_a)

    def test_module_access_denied_for_non_admin_roles(self):
        teacher = User.objects.create_user(
            username="tch",
            password="ComplexPass123!",
            role=User.Role.TEACHER,
            school=self.school_a,
        )
        self.assertFalse(
            self._model_admin().has_module_permission(self._request_for(teacher))
        )

    def test_module_access_allowed_for_school_admin(self):
        self.assertTrue(
            self._model_admin().has_module_permission(self._request_for(self.school_admin))
        )