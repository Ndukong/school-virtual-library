from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from accounts.permissions import (
    AdminOrTeacherRequiredMixin,
    AdminRequiredMixin,
    StudentRequiredMixin,
    TeacherRequiredMixin,
    is_admin,
    is_teacher,
)
from accounts.services import (
    check_login_lock,
    client_ip,
    complete_password_change,
    record_failed_login,
    reset_login_state,
    reset_password,
)


class HomeView(View):
    """Route authenticated users to their role's dashboard."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if is_admin(request.user):
            return redirect("dashboard-admin")
        if is_teacher(request.user):
            return redirect("dashboard-teacher")
        return redirect("dashboard-student")


class LoginView(DjangoLoginView):
    """Login with WP3 lockout: exponential backoff keyed on username+IP.

    A user inside a lock window never reaches the authentication backend and
    sees a plain "too many attempts" message instead of a validity verdict.
    Successes clear the lock's failures for that key.
    """

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        username = (request.POST.get("username") or "").strip()
        ip = client_ip(request)
        blocked, wait = check_login_lock(username, ip)
        if blocked:
            self._blocked = True
            form = self.get_form()
            form.add_error(
                None,
                _("Too many failed attempts. Try again in %(seconds)d second(s).")
                % {"seconds": wait},
            )
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        reset_login_state(user.username, client_ip(self.request))
        if not getattr(user, "must_change_password", False):
            return super().form_valid(form)
        from django.contrib.auth import login as auth_login

        auth_login(self.request, user)
        return HttpResponseRedirect(reverse("force-password-change"))

    def form_invalid(self, form):
        if not getattr(self, "_blocked", False):
            record_failed_login(
                (self.request.POST.get("username") or "").strip(),
                client_ip(self.request),
            )
        return super().form_invalid(form)


class SetLanguageView(View):
    """Language switcher (WP7).

    Open to anonymous users so the login screen itself is bilingual; the
    choice is persisted to the account when the visitor is signed in and is
    also written to Django's language cookie (Django 5.2 resolves the request
    language from that cookie). next is validated to stay same-origin.
    """

    def get(self, request):
        code = (request.GET.get("lang") or "").strip().lower()
        valid = {code for code, _label in settings.LANGUAGES}
        if code in valid and request.user.is_authenticated:
            if code != request.user.language:
                request.user.language = code
                request.user.save(update_fields=["language"])
            translation.activate(code)
        next_url = (request.GET.get("next") or "").strip()
        if not next_url.startswith("/") or next_url.startswith("//"):
            next_url = reverse("home")
        response = HttpResponseRedirect(next_url)
        if code in valid:
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                code,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
                secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
        return response


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    template_name = "accounts/dashboard_admin.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        context["school"] = school
        if school is not None:
            context["counts"] = {
                "classes": school.classes.count(),
                "subjects": school.subjects.count(),
                "teachers": school.teachers.count(),
                "students": school.students.count(),
            }
        return context


class TeacherDashboardView(TeacherRequiredMixin, TemplateView):
    template_name = "accounts/dashboard_teacher.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["teacher_profile"] = getattr(self.request.user, "teacher_profile", None)
        return context


class StudentDashboardView(StudentRequiredMixin, TemplateView):
    template_name = "accounts/dashboard_student.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["student_profile"] = getattr(self.request.user, "student_profile", None)
        return context


class ProfileView(LoginRequiredMixin, TemplateView):
    """Personal hub: account info and role-appropriate links (PWA nav item)."""

    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["school"] = user.school
        context["student_profile"] = getattr(user, "student_profile", None)
        context["teacher_profile"] = getattr(user, "teacher_profile", None)
        return context


class LogoutAllDevicesView(LoginRequiredMixin, View):
    """End every session for the current user except this one."""

    def post(self, request):
        from django.contrib import messages
        from django.contrib.sessions.models import Session

        user_identifier = str(request.user.pk)
        now = timezone.now()
        deleted = 0
        for session in Session.objects.filter(expire_date__gt=now):
            if session.session_key == request.session.session_key:
                continue
            try:
                payload = session.get_decoded()
            except Exception:  # noqa: BLE001 - skip corrupted sessions
                continue
            if str(payload.get("_auth_user_id", "")) == user_identifier:
                session.delete()
                deleted += 1
        messages.success(request, _("Signed out %(count)d other session(s).") % {"count": deleted})
        return redirect("profile")


class ResetPasswordListView(AdminOrTeacherRequiredMixin, TemplateView):
    """Admin/teacher page listing school users for temporary-password resets."""

    template_name = "accounts/reset_list.html"

    def get_context_data(self, **kwargs):
        from django.contrib.auth import get_user_model

        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        users = get_user_model().objects.filter(school=school).order_by("username")
        context["users"] = users
        return context


class ResetPasswordRunView(AdminOrTeacherRequiredMixin, View):
    def _target(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.filter(
            username=(self.request.POST.get("username") or "").strip(),
            school=self.request.user.school,
        ).first()

    def post(self, request):
        target = self._target()
        if target is None:
            messages.error(request, "No matching user in this school.")
            return redirect("password-reset-list")
        temporary = reset_password(request.user, target)
        request.session["_credential_slip"] = {
            "username": target.username,
            "temporary": temporary,
            "must_change": True,
        }
        return redirect("password-reset-slip")


class ResetPasswordSlipView(AdminOrTeacherRequiredMixin, TemplateView):
    """One-time printable credential slip; content is cleared after render."""

    template_name = "accounts/reset_slip.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slip = self.request.session.pop("_credential_slip", None)
        context["slip"] = slip
        return context


class ForcePasswordChangeView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/force_password_change.html"

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, "must_change_password", False):
            return redirect("profile")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", kwargs.pop("form", None))
        if context["form"] is None:
            from accounts.forms import ForcePasswordChangeForm

            context["form"] = ForcePasswordChangeForm(user=self.request.user)
        return context

    def post(self, request):
        from accounts.forms import ForcePasswordChangeForm

        form = ForcePasswordChangeForm(request.POST, user=request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        new_password = form.cleaned_data["new_password1"]
        complete_password_change(request.user, new_password)
        from django.contrib.auth import update_session_auth_hash

        update_session_auth_hash(request, request.user)
        messages.success(request, "Password updated.")
        return redirect("profile")

