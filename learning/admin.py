from django.contrib import admin

from common.admin import SchoolScopedModelAdmin
from learning.models import AttemptResponse, PracticeAttempt


class AttemptResponseInline(admin.TabularInline):
    model = AttemptResponse
    extra = 0
    readonly_fields = ("question", "position", "given_answer", "is_correct",
                       "awarded_marks", "self_marked")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PracticeAttempt)
class PracticeAttemptAdmin(SchoolScopedModelAdmin):
    list_display = ("student", "source_type", "subject", "status",
                    "earned_marks", "possible_marks", "created_at")
    list_filter = ("school", "status", "source_type", "subject")
    search_fields = ("student__username",)
    readonly_fields = ("public_id", "student", "school", "subject", "exam",
                       "topic_filter", "status", "possible_marks", "earned_marks")
    inlines = [AttemptResponseInline]

    # Attempts contain student performance data: view-only for school admins,
    # never editable here (privacy + integrity).
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AttemptResponse)
class AttemptResponseAdmin(admin.ModelAdmin):
    list_display = ("attempt", "position", "question", "is_correct", "awarded_marks")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(attempt__school=request.user.school)
        return qs.none()

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser