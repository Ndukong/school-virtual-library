from django.contrib import admin

from accounts.permissions import is_admin
from common.admin import SchoolScopedModelAdmin
from common.audit import record as audit_record
from library.models import BookChapter, BookSection, Resource


class ResourceChainScopedAdminMixin:
    """Scope admins of models without a direct school FK (chapters, sections).

    Visibility follows the resource chain back to the school; permissions
    mirror SchoolScopedModelAdmin's rules.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return self._scoped(qs, request)
        return qs.none()

    def _scoped(self, queryset, request):
        raise NotImplementedError

    def has_module_permission(self, request):
        return request.user.is_superuser or is_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or is_admin(request.user)

    def has_add_permission(self, request):
        return request.user.is_superuser or is_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or is_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or is_admin(request.user)


class BookSectionInline(admin.StackedInline):
    model = BookSection
    extra = 0


class BookChapterInline(admin.StackedInline):
    model = BookChapter
    extra = 0


@admin.register(Resource)
class ResourceAdmin(SchoolScopedModelAdmin):
    list_display = (
        "title",
        "resource_type",
        "school",
        "subject",
        "school_class",
        "access_policy",
        "licensing_status",
        "processing_status",
        "is_active",
    )
    list_filter = (
        "school",
        "resource_type",
        "access_policy",
        "licensing_status",
        "processing_status",
        "is_active",
    )
    search_fields = ("title", "author", "isbn", "publisher", "school__name")
    readonly_fields = ("public_id", "original_filename", "file_size", "created_at", "updated_at")

    inlines = [BookChapterInline]

    def delete_model(self, request, obj):
        audit_record(
            actor=request.user,
            action="resource.admin_delete",
            target_type="Resource",
            target_id=str(obj.public_id),
            detail=f"{obj.title} (school: {obj.school})",
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        rows = list(
            queryset.values_list("public_id", "title", "school_id")
        )
        super().delete_queryset(request, queryset)
        for public_id, title, school_id in rows:
            audit_record(
                actor=request.user,
                action="resource.admin_delete",
                target_type="Resource",
                target_id=str(public_id),
                detail=f"{title} (school: {school_id})",
            )


@admin.register(BookChapter)
class BookChapterAdmin(ResourceChainScopedAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "resource", "start_page", "end_page")
    search_fields = ("title", "resource__title")

    def _scoped(self, queryset, request):
        return queryset.filter(resource__school=request.user.school)


@admin.register(BookSection)
class BookSectionAdmin(ResourceChainScopedAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "chapter", "start_page", "end_page")
    search_fields = ("title", "chapter__title", "chapter__resource__title")

    def _scoped(self, queryset, request):
        return queryset.filter(chapter__resource__school=request.user.school)