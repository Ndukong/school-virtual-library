from django.contrib import admin

from common.admin import SchoolRestrictedInlineMixin, SchoolScopedModelAdmin
from teachers.models import Teacher


class TeacherInline(SchoolRestrictedInlineMixin, admin.StackedInline):
    model = Teacher
    extra = 0
    filter_horizontal = ("subjects",)
    fields = ("school", "staff_number", "subjects", "is_active")


@admin.register(Teacher)
class TeacherAdmin(SchoolScopedModelAdmin):
    list_display = ("user", "staff_number", "school", "is_active")
    list_filter = ("school", "is_active")
    search_fields = (
        "staff_number",
        "user__username",
        "user__first_name",
        "user__last_name",
        "school__name",
    )
    filter_horizontal = ("subjects",)