from django.views.generic import TemplateView

from accounts.permissions import AdminOrTeacherRequiredMixin
from reports.services import (
    ai_stats,
    library_stats,
    popular_topics,
    practice_stats,
    teacher_activity,
)
from schools.models import School


class ReportBaseMixin(AdminOrTeacherRequiredMixin):
    """Staff-only analytics; scope to the requestor's school unless they are
    a platform superuser (who chooses a school via ?school=)."""

    def resolve_school(self):
        user = self.request.user
        if user.is_superuser:
            school_id = self.request.GET.get("school")
            if school_id and school_id.isdigit():
                return School.objects.filter(id=int(school_id), is_active=True).first()
            return None if user.school_id is None else user.school
        return user.school


class ReportHubView(ReportBaseMixin, TemplateView):
    template_name = "reports/report_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["schools"] = School.objects.filter(is_active=True) if user.is_superuser else School.objects.none()
        context["selected_school"] = self.resolve_school()
        return context


class _StatsMixin(ReportBaseMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_school"] = self.resolve_school()
        return context


class LibraryReportView(_StatsMixin, TemplateView):
    template_name = "reports/library.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = context["selected_school"]
        context["stats"] = library_stats(school) if school else None
        return context


class AIReportView(_StatsMixin, TemplateView):
    template_name = "reports/ai.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = context["selected_school"]
        context["stats"] = ai_stats(school) if school else None
        return context


class PracticeReportView(_StatsMixin, TemplateView):
    template_name = "reports/practice.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = context["selected_school"]
        if school:
            context["stats"] = practice_stats(school)
            context["topics"] = popular_topics(school)
        else:
            context["stats"] = None
            context["topics"] = []
        return context


class TeachersReportView(_StatsMixin, TemplateView):
    template_name = "reports/teachers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = context["selected_school"]
        context["stats"] = teacher_activity(school) if school else []
        return context