from django.contrib import admin

from classes.models import SchoolClass
from common.admin import SchoolScopedModelAdmin


@admin.register(SchoolClass)
class SchoolClassAdmin(SchoolScopedModelAdmin):
    list_display = ("name", "school", "is_active")
    list_filter = ("school", "is_active")
    search_fields = ("name", "school__name")