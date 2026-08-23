from django.contrib import admin

from common.admin import SchoolRestrictedInlineMixin
from documents.models import DocumentChunk, ExtractedPage, ProcessingJob, ProcessingLog
from library.admin import ResourceChainScopedAdminMixin


@admin.register(ExtractedPage)
class ExtractedPageAdmin(ResourceChainScopedAdminMixin, admin.ModelAdmin):
    list_display = ("resource", "page_number", "has_text")
    list_filter = ("has_text",)
    search_fields = ("resource__title",)

    def _scoped(self, queryset, request):
        return queryset.filter(resource__school=request.user.school)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(ResourceChainScopedAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "page_start", "page_end", "chapter", "section")
    search_fields = ("text", "resource__title")

    def _scoped(self, queryset, request):
        return queryset.filter(resource__school=request.user.school)


@admin.register(ProcessingLog)
class ProcessingLogAdmin(ResourceChainScopedAdminMixin, admin.ModelAdmin):
    list_display = ("resource", "level", "message", "created_at")
    list_filter = ("level",)
    search_fields = ("message", "resource__title")
    readonly_fields = ("resource", "level", "message", "created_at")

    def _scoped(self, queryset, request):
        return queryset.filter(resource__school=request.user.school)

    def has_add_permission(self, request):
        return False


class ProcessingLogInline(SchoolRestrictedInlineMixin, admin.TabularInline):
    model = ProcessingLog
    extra = 0
    readonly_fields = ("level", "message", "created_at")
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProcessingJob)
class ProcessingJobAdmin(ResourceChainScopedAdminMixin, admin.ModelAdmin):
    list_display = ("resource", "step", "status", "attempts", "last_error", "updated_at")
    list_filter = ("status", "step")
    search_fields = ("resource__title",)
    readonly_fields = ("public_id", "resource", "step", "attempts", "max_attempts",
                       "last_error", "started_at", "finished_at", "created_at", "updated_at")

    def _scoped(self, queryset, request):
        return queryset.filter(resource__school=request.user.school)

    def has_add_permission(self, request):
        # Jobs are created by the application/dispatcher only.
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser