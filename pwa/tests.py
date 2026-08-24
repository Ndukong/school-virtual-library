import json

from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from schools.models import School

PASSWORD = "ComplexPass123!"


class ManifestTests(TestCase):
    def test_manifest_json_contract(self):
        response = Client().get(reverse("pwa-manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        manifest = json.loads(response.content)
        self.assertEqual(manifest["name"], "School Virtual Library")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(len(manifest["icons"]), 2)
        purposes = {icon["purpose"] for icon in manifest["icons"]}
        self.assertEqual(purposes, {"any", "maskable"})


class ServiceWorkerTests(TestCase):
    def test_served_with_root_scope_and_no_store(self):
        response = Client().get(reverse("pwa-sw"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_worker_has_expected_content_markers(self):
        with open(finders.find("pwa/sw.js"), encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("svl-shell-v2", body)
        self.assertIn('"/offline/"', body)
        self.assertIn("request.mode === \"navigate\"", body)
        self.assertIn("network", body.lower())

    def test_register_script_exists_for_precache(self):
        self.assertIsNotNone(finders.find("pwa/sw-register.js"))
        self.assertIsNotNone(finders.find("pwa/sw.js"))
        self.assertIsNotNone(finders.find("pwa/icons/icon.svg"))
        self.assertIsNotNone(finders.find("pwa/icons/icon-maskable.svg"))


class OfflineViewTests(TestCase):
    def test_offline_shell_renders(self):
        response = Client().get(reverse("pwa-offline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "offline")


class PwaIntegrationTests(TestCase):
    """Shell pages still render with PWA wiring (manifest/registration)."""

    def setUp(self):
        self.school = School.objects.create(name="Alpha Academy")
        self.student = User.objects.create_user(
            "stua", password=PASSWORD, role=User.Role.STUDENT, school=self.school
        )

    def test_login_page_links_manifest(self):
        client = Client()
        response = client.get(reverse("login"))
        self.assertContains(response, "manifest.webmanifest")
        self.assertContains(response, "sw-register.js")

    def test_profile_page_for_student(self):
        from django.urls import reverse as rev

        client = Client()
        client.force_login(self.student)
        response = client.get(rev("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My practice progress")
        self.assertContains(response, self.school.name)

    def test_anonymous_profile_redirects_to_login(self):
        response = Client().get(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


class OfflineFirstTests(TestCase):
    """WP8: worker must not auto-cache app pages, and the offline bundles
    (reader / practice / clear) must ship."""

    def test_worker_precaches_only_the_static_shell(self):
        with open(finders.find("pwa/sw.js"), encoding="utf-8") as handle:
            body = handle.read()
        # The worker never writes to the user's device caches (svl-files-v1 /
        # svl-attempts-v1); those are built by the page scripts. Its only
        # cache writes go to the shell (static stale-while-revalidate).
        self.assertEqual(
            body.count("caches.open("),
            body.count("caches.open(SHELL_CACHE)"),
        )
        # Only the shell is precached; app pages are never in PRECACHE_SHELL.
        install_start = body.index("PRECACHE_SHELL")
        install_end = body.index("install", install_start)
        install_section = body[install_start:install_end]
        for item in ("/offline/", "site.css", "manifest.webmanifest"):
            self.assertIn(item, install_section)
        self.assertNotIn("/library/", install_section)
        self.assertNotIn("/practice/", install_section)
        # The offline fallback reads caches the user built.
        self.assertIn('caches.match(request)', body)
        self.assertIn('caches.match("/offline/")', body)

    def test_offline_bundles_are_shipped(self):
        for name in (
            "pwa/sw-register.js",
            "pwa/offline-reader.js",
            "pwa/offline-practice.js",
            "pwa/offline-clear.js",
        ):
            self.assertIsNotNone(finders.find(name), name)
        with open(finders.find("pwa/offline-clear.js"), encoding="utf-8") as handle:
            clear_body = handle.read()
        self.assertIn("svl-files-v1", clear_body)
        self.assertIn("svl-attempts-v1", clear_body)

    def test_manifest_reflects_active_language(self):
        client = Client()
        client.cookies["django_language"] = "fr"
        response = client.get(reverse("pwa-manifest"))
        manifest = json.loads(response.content)
        self.assertEqual(manifest["lang"], "fr")

    def test_offline_shell_is_bilingual(self):
        client = Client()
        client.cookies["django_language"] = "fr"
        response = client.get(reverse("pwa-offline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vous êtes hors ligne")

    def test_login_page_includes_offline_cache_clear(self):
        response = Client().get(reverse("login"))
        self.assertContains(response, "offline-clear.js")