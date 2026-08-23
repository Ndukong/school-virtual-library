from django.contrib import admin

from common.admin import PlatformOnlyModelAdmin
from schools.models import School


@admin.register(School)
class SchoolAdmin(PlatformOnlyModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)