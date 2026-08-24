from django.contrib.admin import site as default_admin_site
from django.contrib.auth.models import AnonymousUser
from django.core.management import CommandError, call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.admin import UserAdmin
from accounts.models import LoginFailure, LoginLock, User
from accounts.permissions import has_role, is_admin, is_student, is_teacher
from accounts.services import (
    check_login_lock,
    reset_password,
    reset_user_locks,
)
from common.models import AuditEvent
from schools.models import School

PASSWORD = "ComplexPass123!"


def make_school(name):
    return School.objects.create(name=name)


def make_user(username, role=None, school=None, **extra):
    return User.objects.create_user(
        username=username,
        password=PASSWORD,
        role=role or User.Role.STUDENT,
        school=school,
        **extra,
    )


class UserModelTests(TestCase):
    def test_default_role_is_least_privileged(self):
        user = make_user("u1")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.get_role_display(), "Student")


class PermissionFunctionTests(TestCase):
    def setUp(self):
        self.school = make_school("Alpha Academy")
        self.admin = make_user("adm", User.Role.ADMIN, self.school)
        self.teacher = make_user("tch", User.Role.TEACHER, self.school)
        self.student = make_user("stu", User.Role.STUDENT, self.school)
        self.superuser = make_user("root", User.Role.STUDENT, is_superuser=True)

    def test_is_admin_for_role_and_superuser_only(self):
        self.assertTrue(is_admin(self.admin))
        self.assertTrue(is_admin(self.superuser))
        self.assertFalse(is_admin(self.teacher))
        self.assertFalse(is_admin(self.student))

    def test_teacher_and_student_checks_are_strict(self):
        self.assertTrue(is_teacher(self.teacher))
        self.assertFalse(is_teacher(self.superuser))
        self.assertTrue(is_student(self.student))
        self.assertFalse(is_student(self.superuser))

    def test_anonymous_user_has_no_roles(self):
        anonymous = AnonymousUser()
        self.assertFalse(has_role(anonymous, "ADMIN"))
        self.assertFalse(is_admin(anonymous))
        self.assertFalse(is_teacher(anonymous))
        self.assertFalse(is_student(anonymous))


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.school = make_school("Alpha Academy")
        self.admin = make_user("adm", User.Role.ADMIN, self.school)
        self.teacher = make_user("tch", User.Role.TEACHER, self.school)
        self.student = make_user("stu", User.Role.STUDENT, self.school)
        self.superuser = make_user("root", is_superuser=True)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dashboard-admin"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_student_forbidden_on_admin_dashboard(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("dashboard-admin")).status_code, 403)

    def test_teacher_forbidden_on_admin_dashboard(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("dashboard-admin")).status_code, 403)

    def test_teacher_forbidden_on_student_dashboard(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("dashboard-student")).status_code, 403)

    def test_student_forbidden_on_teacher_dashboard(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("dashboard-teacher")).status_code, 403)

    def test_admin_sees_own_school_on_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard-admin"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Academy")

    def test_superuser_allowed_on_admin_dashboard(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("dashboard-admin")).status_code, 200)

    def test_student_sees_profile_details(self):
        from students.models import Student

        Student.objects.create(user=self.student, school=self.school, admission_number="A-9")
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboard-student"))
        self.assertContains(response, "A-9")

    def test_teacher_without_profile_gets_notice(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("dashboard-teacher"))
        self.assertContains(response, "No teacher profile")


class HomeRedirectTests(TestCase):
    def setUp(self):
        self.school = make_school("Alpha Academy")
        self.admin = make_user("adm", User.Role.ADMIN, self.school)
        self.teacher = make_user("tch", User.Role.TEACHER, self.school)
        self.student = make_user("stu", User.Role.STUDENT, self.school)

    def test_anonymous_home_goes_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_each_role_routes_to_its_dashboard(self):
        expected = {
            self.admin: reverse("dashboard-admin"),
            self.teacher: reverse("dashboard-teacher"),
            self.student: reverse("dashboard-student"),
        }
        for user, dashboard in expected.items():
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("home"), follow=True)
                self.assertEqual(response.request["PATH_INFO"], dashboard)
                self.client.logout()


class AuthFlowTests(TestCase):
    def setUp(self):
        self.school = make_school("Alpha Academy")
        self.admin = make_user("adm", User.Role.ADMIN, self.school)

    def test_login_page_renders_form(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")

    def test_login_rejects_bad_credentials(self):
        response = self.client.post(
            reverse("login"), {"username": "adm", "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct username")

    def test_login_redirects_to_role_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "adm", "password": PASSWORD},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("dashboard-admin"))

    def test_authenticated_user_hitting_login_is_redirected(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 302)

    def test_logout_requires_post_then_blocks_access(self):
        self.client.force_login(self.admin)
        get_response = self.client.get(reverse("logout"))
        self.assertIn(get_response.status_code, (302, 405))
        post_response = self.client.post(reverse("logout"))
        self.assertEqual(post_response.status_code, 302)
        self.assertIn("/login/", post_response.url)
        self.assertEqual(self.client.get(reverse("dashboard-admin")).status_code, 302)


class UserAdminScopingTests(TestCase):
    def setUp(self):
        self.school_a = make_school("Alpha Academy")
        self.school_b = make_school("Beta High")
        self.school_admin = make_user(
            "schooladmin", User.Role.ADMIN, self.school_a, is_staff=True
        )
        self.other_school_admin = make_user(
            "otheradmin", User.Role.ADMIN, self.school_b, is_staff=True
        )
        self.superuser = make_user("root", is_superuser=True)
        self.factory = RequestFactory()
        self.model_admin = UserAdmin(User, default_admin_site)

    def _request_for(self, user):
        request = self.factory.get("/admin/accounts/user/")
        request.user = user
        return request

    def test_school_admin_sees_only_own_school_users(self):
        queryset = self.model_admin.get_queryset(self._request_for(self.school_admin))
        usernames = set(queryset.values_list("username", flat=True))
        self.assertIn("schooladmin", usernames)
        self.assertNotIn("otheradmin", usernames)
        self.assertNotIn("root", usernames)

    def test_superuser_sees_all_users(self):
        queryset = self.model_admin.get_queryset(self._request_for(self.superuser))
        self.assertEqual(queryset.count(), User.objects.count())

    def test_save_model_forces_school_and_prevents_escalation(self):
        newcomer = User(username="newbie", role=User.Role.TEACHER)
        newcomer.school = self.school_b
        newcomer.is_staff = True
        newcomer.is_superuser = True
        self.model_admin.save_model(
            self._request_for(self.school_admin), newcomer, form=None, change=False
        )
        newcomer.refresh_from_db()
        self.assertEqual(newcomer.school, self.school_a)
        self.assertFalse(newcomer.is_staff)
        self.assertFalse(newcomer.is_superuser)


class CreateSchoolAdminCommandTests(TestCase):
    def test_creates_school_and_administrator(self):
        call_command(
            "create_school_admin",
            school="Hill High School",
            username="principal",
            email="p@hill.example",
            password="Strong-Pass-123",
        )
        school = School.objects.get(name="Hill High School")
        user = User.objects.get(username="principal")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertEqual(user.school, school)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("Strong-Pass-123"))

    def test_reuses_existing_school(self):
        existing = make_school("Hill High School")
        call_command(
            "create_school_admin",
            school="Hill High School",
            username="deputy",
            password="Strong-Pass-123",
        )
        self.assertEqual(School.objects.filter(name="Hill High School").count(), 1)
        self.assertEqual(User.objects.get(username="deputy").school, existing)

    def test_duplicate_username_raises(self):
        make_user("principal", User.Role.TEACHER)
        with self.assertRaises(CommandError):
            call_command(
                "create_school_admin",
                school="Hill High School",
                username="principal",
                password="Strong-Pass-123",
            )

    def test_weak_password_raises(self):
        with self.assertRaises(CommandError):
            call_command(
                "create_school_admin",
                school="Hill High School",
                username="weakpw",
                password="123",
)


class LogoutAllDevicesTests(TestCase):
    def setUp(self):
        self.school = make_school("Logout School")
        self.user_a = make_user("la", User.Role.STUDENT, self.school)
        self.user_b = make_user("lb", User.Role.STUDENT, self.school)

    def test_signs_out_other_sessions_keeps_current_and_other_users(self):
        client_a1 = Client()
        client_a1.force_login(self.user_a)
        client_a1.get(reverse("profile"))
        client_a2 = Client()
        client_a2.force_login(self.user_a)
        client_a2.get(reverse("profile"))
        client_b = Client()
        client_b.force_login(self.user_b)
        client_b.get(reverse("profile"))

        response = client_a1.post(reverse("logout-all"))
        self.assertEqual(response.status_code, 302)

        self.assertEqual(client_a1.get(reverse("profile")).status_code, 200)  # current kept
        self.assertEqual(client_a2.get(reverse("profile")).status_code, 302)  # other device out
        self.assertEqual(client_b.get(reverse("profile")).status_code, 200)   # other user intact

    def test_logout_all_requires_post_and_login(self):
        client = Client()
        response = client.get(reverse("logout-all"))
        self.assertIn(response.status_code, (302, 405))
        client.force_login(self.user_a)
        self.assertEqual(client.get(reverse("logout-all")).status_code in (302, 405), True)

@override_settings(LOGIN_LOCKOUT_BASE_SECONDS=5)
class LoginLockoutTests(TestCase):
    def setUp(self):
        self.school = make_school("Lock School")
        self.user = make_user("lockstudent", User.Role.STUDENT, self.school)

    def test_first_failure_locks_then_blocks_before_auth(self):
        client = Client()
        first = client.post(reverse("login"), {"username": "lockstudent", "password": "wrong"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(LoginFailure.objects.count(), 1)
        second = client.post(reverse("login"), {"username": "lockstudent", "password": "wrong"})
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "Too many failed attempts")
        self.assertEqual(LoginFailure.objects.count(), 1)  # blocked, not re-audited
        blocked, wait = check_login_lock("lockstudent", "127.0.0.1")
        self.assertTrue(blocked)
        self.assertGreaterEqual(wait, 1)

    def test_lock_is_keyed_per_ip(self):
        client = Client()
        client.post(reverse("login"), {"username": "lockstudent", "password": "wrong"})
        blocked_a, _ = check_login_lock("lockstudent", "127.0.0.1")
        blocked_b, _ = check_login_lock("lockstudent", "203.0.113.7")
        self.assertTrue(blocked_a)
        self.assertFalse(blocked_b)

    def test_success_login_clears_lock_and_resets_wait(self):

        LoginFailure.objects.create(username="lockstudent", ip="127.0.0.1")
        # Stale, already-expired lock: must not block, then gets cleared.
        LoginLock.objects.create(
            username="lockstudent", ip="127.0.0.1", attempts=12,
            locked_until=timezone.now() - timezone.timedelta(minutes=1),
        )
        client = Client()
        response = client.post(reverse("login"), {"username": "lockstudent", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LoginLock.objects.filter(username="lockstudent", ip="127.0.0.1").exists())
        self.assertFalse(LoginFailure.objects.filter(username="lockstudent", ip="127.0.0.1").exists())

    def test_admin_unlock_clears_all_keys(self):

        LoginFailure.objects.create(username="lockstudent", ip="127.0.0.1")
        LoginLock.objects.create(username="lockstudent", ip="127.0.0.1",
                                 attempts=3, locked_until=timezone.now() + timezone.timedelta(minutes=5))
        reset_user_locks("lockstudent")
        blocked, _ = check_login_lock("lockstudent", "127.0.0.1")
        self.assertFalse(blocked)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.school = make_school("Reset School")
        self.admin = make_user("resetadmin", User.Role.ADMIN, self.school, is_staff=True)
        self.student = make_user("resetstudent", User.Role.STUDENT, self.school)
        self.other_student = make_user("otherstudent", User.Role.STUDENT, self.school)
        self.other_school_admin = make_user(
            "otherresetadmin", User.Role.ADMIN, make_school("Other Reset"), is_staff=True
        )

    def test_reset_sets_temp_password_and_audits(self):
        from accounts.models import PasswordReset

        temporary = reset_password(self.admin, self.student)
        self.student.refresh_from_db()
        self.assertTrue(self.student.must_change_password)
        self.assertTrue(self.student.check_password(temporary))
        reset = PasswordReset.objects.get(target_user=self.student)
        self.assertEqual(reset.admin_user, self.admin)
        self.assertIsNone(reset.completed_at)

    def test_logged_out_temp_login_redirects_to_forced_change(self):
        temporary = reset_password(self.admin, self.student)
        client = Client()
        response = client.post(
            reverse("login"), {"username": "resetstudent", "password": temporary}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("force-password-change"))

    def test_forced_change_clears_flag_and_invalidates_temp(self):
        temporary = reset_password(self.admin, self.student)
        client = Client()
        client.post(reverse("login"), {"username": "resetstudent", "password": temporary})
        page = client.get(reverse("force-password-change"))
        self.assertEqual(page.status_code, 200)
        client.post(
            reverse("force-password-change"),
            {"new_password1": "NewSecurePass123!", "new_password2": "NewSecurePass123!"},
            follow=True,
        )
        self.student.refresh_from_db()
        self.assertFalse(self.student.must_change_password)
        self.assertTrue(self.student.check_password("NewSecurePass123!"))
        self.assertTrue(
            self.student.password_resets.filter(completed_at__isnull=False).exists()
        )
        # Temporary password no longer works.
        client.logout()
        failed = client.post(reverse("login"), {"username": "resetstudent", "password": temporary})
        self.assertEqual(failed.status_code, 200)

    def test_must_change_middleware_redirects_everywhere_else(self):
        reset_password(self.admin, self.student)
        client = Client()
        client.force_login(self.student)
        self.assertEqual(client.get(reverse("library-list")).status_code, 302)
        self.assertEqual(
            client.get(reverse("library-list")).url, reverse("force-password-change")
        )

    def test_student_cannot_use_reset_area(self):
        client = Client()
        client.force_login(self.student)
        self.assertEqual(client.get(reverse("password-reset-list")).status_code, 403)

    def test_admin_reset_flow_via_views_with_one_time_slip(self):
        client = Client()
        client.force_login(self.admin)
        response = client.post(
            reverse("password-reset-run"), {"username": "otherstudent"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password-reset-slip"))
        slip_page = client.get(reverse("password-reset-slip"))
        self.assertContains(slip_page, "otherstudent")
        # One-time only.
        second = client.get(reverse("password-reset-slip"))
        self.assertNotContains(second, "otherstudent")

    def test_cross_school_staff_cannot_reset(self):
        client = Client()
        client.force_login(self.other_school_admin)
        response = client.post(
            reverse("password-reset-run"), {"username": "resetstudent"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password-reset-list"))
        self.student.refresh_from_db()
        self.assertFalse(self.student.must_change_password)


class BilingualUserTests(TestCase):
    """WP7: per-user language, switcher persistence, and French UI."""

    def setUp(self):
        self.school = make_school("Alpha Academy")
        self.student = make_user("stufr", User.Role.STUDENT, self.school)

    def test_language_default_is_english(self):
        self.assertEqual(self.student.language, "en")
        self.assertEqual(self.student.get_language_display(), "English")

    def test_switcher_persists_user_language_and_sets_cookie(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("set-language") + "?lang=fr&next=/profile/")
        self.assertRedirects(response, "/profile/")
        self.student.refresh_from_db()
        self.assertEqual(self.student.language, "fr")
        self.assertEqual(response.cookies["django_language"].value, "fr")

    def test_switcher_rejects_foreign_next(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("set-language") + "?lang=en&next=https://evil.example/phish"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_french_ui_rendered_for_french_user(self):
        self.student.language = "fr"
        self.student.save(update_fields=["language"])
        self.client.force_login(self.student)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Liens rapides")
        self.assertContains(response, "Déconnexion")
        self.assertContains(response, "Bibliothèque")
        self.assertEqual(response["Content-Language"], "fr")

    def test_english_ui_rendered_for_english_user(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Quick links")
        self.assertContains(response, "Log out")

    def test_anonymous_switch_makes_login_screen_french(self):
        self.client.get(reverse("set-language") + "?lang=fr&next=/login/")
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Connexion")
        self.assertContains(response, "Nom d'utilisateur")
        self.assertContains(response, "Mot de passe")


class GovernanceAuditTests(TestCase):
    """WP9: privileged admin actions leave an append-only audit trail."""

    def setUp(self):
        self.school = make_school("Audit Academy")
        self.superuser = make_user("root", User.Role.STUDENT, is_superuser=True)
        self.school_admin = make_user("adm", User.Role.ADMIN, self.school, is_staff=True)
        self.student = make_user("stuaudit", User.Role.STUDENT, self.school)

    def test_role_change_is_audited_with_before_and_after(self):
        admin_instance = default_admin_site._registry[User]
        request = RequestFactory().get("/admin/accounts/user/1/change/")
        request.user = self.superuser

        changed = User.objects.get(pk=self.student.pk)
        changed.role = User.Role.TEACHER
        admin_instance.save_model(request, changed, None, change=True)

        event = AuditEvent.objects.filter(
            action="user.admin_change", target_id=self.student.username
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.actor, self.superuser)
        self.assertIn("role:STUDENT->TEACHER", event.detail)

    def test_no_audit_event_when_nothing_changed(self):
        admin_instance = default_admin_site._registry[User]
        request = RequestFactory().get("/admin/accounts/user/1/change/")
        request.user = self.superuser

        unchanged = User.objects.get(pk=self.student.pk)
        admin_instance.save_model(request, unchanged, None, change=True)
        self.assertFalse(
            AuditEvent.objects.filter(action="user.admin_change").exists()
        )

    def test_user_delete_is_audited(self):
        admin_instance = default_admin_site._registry[User]
        request = RequestFactory().post("/admin/accounts/user/")
        request.user = self.superuser
        admin_instance.delete_queryset(
            request, User.objects.filter(pk=self.student.pk)
        )
        event = AuditEvent.objects.filter(
            action="user.admin_delete", target_id=self.student.username
        ).first()
        self.assertIsNotNone(event)
        self.assertFalse(User.objects.filter(pk=self.student.pk).exists())

    def test_audit_admin_is_superuser_only_and_append_only(self):
        audit_admin = default_admin_site._registry[AuditEvent]
        from django.test import RequestFactory

        superuser_request = RequestFactory().get("/admin/common/auditevent/")
        superuser_request.user = self.superuser
        admin_request = RequestFactory().get("/admin/common/auditevent/")
        admin_request.user = self.school_admin

        self.assertTrue(audit_admin.has_view_permission(superuser_request))
        self.assertFalse(audit_admin.has_view_permission(admin_request))
        self.assertFalse(audit_admin.has_add_permission(superuser_request))
        self.assertFalse(audit_admin.has_change_permission(superuser_request))
        self.assertFalse(audit_admin.has_delete_permission(superuser_request))


class DataSubjectExportTests(TestCase):
    """WP9: `export_user_data` produces one user's own data, nothing else."""

    def setUp(self):
        self.school = make_school("Export Academy")
        self.student_a = make_user("expa", User.Role.STUDENT, self.school)
        self.student_b = make_user("expb", User.Role.STUDENT, self.school)
        from ai.models import AIGeneration, AIInteraction
        from learning.models import AttemptResponse, PracticeAttempt
        from question_bank.models import Question
        from subjects.models import Subject

        self.interaction_a = AIInteraction.objects.create(
            user=self.student_a, school=self.school,
            question="SECRET QUESTION A", answer="SECRET ANSWER A",
            used_provider=True,
        )
        AIInteraction.objects.create(
            user=self.student_b, school=self.school,
            question="SECRET QUESTION B", answer="SECRET ANSWER B", used_provider=True,
        )
        AIGeneration.objects.create(
            user=self.student_a, school=self.school, kind="SUMMARY",
            scope="LIBRARY", content="SECRET NOTES A", used_provider=True,
        )
        physics = Subject.objects.create(school=self.school, name="Physics")
        question = Question.objects.create(
            school=self.school, subject=physics, body="Body placeholder",
            correct_answer="X", question_type=Question.QuestionType.SHORT_STRUCTURED,
            marks=2, author=self.student_a,
        )
        attempt = PracticeAttempt.objects.create(
            student=self.student_a, school=self.school,
            source_type=PracticeAttempt.Source.SELF_QUIZ,
            topic_filter="", possible_marks=2,
        )
        AttemptResponse.objects.create(
            attempt=attempt, question=question, position=1,
            given_answer="MY GIVEN ANSWER A",
        )

    def test_export_contains_only_the_subject_user_data(self):
        import json
        import tempfile
        from pathlib import Path

        from django.core.management import call_command

        out = Path(tempfile.gettempdir()) / f"svl_export_{self.student_a.pk}_{self.student_a.username}.json"
        if out.exists():
            out.unlink()
        call_command("export_user_data", self.student_a.username, "--out", str(out))
        payload = json.loads(out.read_text(encoding="utf-8"))
        out.unlink()

        self.assertEqual(payload["user"]["username"], "expa")
        self.assertEqual(payload["school"], "Export Academy")
        self.assertEqual(len(payload["ai_interactions"]), 1)
        self.assertEqual(payload["ai_interactions"][0]["question"], "SECRET QUESTION A")
        self.assertEqual(payload["ai_generations"][0]["content"], "SECRET NOTES A")
        self.assertEqual(
            payload["practice_attempts"][0]["responses"][0]["given_answer"],
            "MY GIVEN ANSWER A",
        )
        dump = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("SECRET QUESTION B", dump)
        self.assertNotIn("SECRET ANSWER B", dump)

    def test_export_refuses_missing_user_and_overwrite(self):
        import tempfile
        from pathlib import Path

        from django.core.management.base import CommandError

        missing = Path(tempfile.gettempdir()) / "svl_export_missing.json"
        if missing.exists():
            missing.unlink()
        with self.assertRaises(CommandError):
            call_command("export_user_data", "ghost", "--out", str(missing))

        out = Path(tempfile.gettempdir()) / f"svl_export_static_{self.student_a.username}.json"
        out.write_text("{}", encoding="utf-8")
        try:
            with self.assertRaises(CommandError):
                call_command("export_user_data", self.student_a.username, "--out", str(out))
        finally:
            out.unlink()
