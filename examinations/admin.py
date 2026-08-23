from django.contrib import admin

from common.admin import SchoolScopedModelAdmin
from examinations.models import Exam, ExamQuestion


class ExamQuestionInline(admin.TabularInline):
    model = ExamQuestion
    extra = 0


@admin.register(Exam)
class ExamAdmin(SchoolScopedModelAdmin):
    list_display = (
        "title", "subject", "school_class", "total_marks",
        "duration_minutes", "status", "created_by",
    )
    list_filter = ("school", "status", "subject")
    search_fields = ("title", "subject__name")
    readonly_fields = ("public_id", "created_by", "config", "created_at", "updated_at")
    inlines = [ExamQuestionInline]


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("exam", "position", "question", "marks")
    search_fields = ("exam__title",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(exam__school=request.user.school)
        return qs.none()

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser