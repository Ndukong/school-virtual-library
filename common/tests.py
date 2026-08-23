"""Phase 0 configuration smoke tests.

Verify the project scaffolding is correctly wired: settings load from the
environment, the common app is registered, and URL configuration imports.
"""

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase


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