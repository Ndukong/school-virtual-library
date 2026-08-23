from django.contrib import admin

from common.admin import SchoolRestrictedInlineMixin, SchoolScopedModelAdmin
from students.models import Student


class StudentInline(SchoolRestrictedInlineMixin, admin.StackedInline):
    model = Student
    extra = 0
    fields = ("school", "school_class", "admission_number", "is_active")


@admin.register(Student)
class StudentAdmin(SchoolScopedModelAdmin):
    list_display = ("admission_number", "user", "school", "school_class", "is_active")
    list_filter = ("school", "is_active")
    search_fields = (
        "admission_number",
        "user__username",
        "user__first_name",
        "user__last_name",
        "school__name",
    )