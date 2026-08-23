from django.contrib import admin

from common.admin import SchoolScopedModelAdmin
from subjects.models import Subject


@admin.register(Subject)
class SubjectAdmin(SchoolScopedModelAdmin):
    list_display = ("name", "code", "school", "is_active")
    list_filter = ("school", "is_active")
    search_fields = ("name", "code", "school__name")