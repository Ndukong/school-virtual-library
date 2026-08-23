from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.permissions import (
    AdminRequiredMixin,
    StudentRequiredMixin,
    TeacherRequiredMixin,
    is_admin,
    is_teacher,
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
    template_name = "registration/login.html"
    redirect_authenticated_user = True


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
        messages.success(request, f"Signed out {deleted} other session(s).")
        return redirect("profile")