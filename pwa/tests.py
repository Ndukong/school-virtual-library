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
        self.assertIn("svl-shell-v1", body)
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