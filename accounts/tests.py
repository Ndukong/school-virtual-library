from django.contrib.admin import site as default_admin_site
from django.contrib.auth.models import AnonymousUser
from django.core.management import CommandError, call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.admin import UserAdmin
from accounts.models import User
from accounts.permissions import has_role, is_admin, is_student, is_teacher
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
        self.assertContains(response, "didn't match")

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