from django.contrib import admin

from accounts.permissions import is_admin
from common.models import AuditEvent
from schools.models import School


class SchoolScopedModelAdmin(admin.ModelAdmin):
    """Base admin for models with a ``school`` ForeignKey.

    Security model:
    - Non-superuser administrators only see objects of their own school.
    - On every save by a non-superuser, ``school`` is forced to the admin's
      own school, so an object can never be moved across schools.
    - Foreign keys and many-to-many fields pointing at school-scoped models
      are filtered to the administrator's own school.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(school=request.user.school)
        return qs.none()

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.school = request.user.school
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            target = db_field.remote_field.model
            if target is School and request.user.school_id:
                kwargs["queryset"] = School.objects.filter(pk=request.user.school_id)
            elif hasattr(target, "school") and request.user.school_id:
                # FK to a school-scoped model (e.g. classes, subjects, users).
                kwargs["queryset"] = target.objects.filter(school=request.user.school)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            target = db_field.remote_field.model
            if hasattr(target, "school") and request.user.school_id:
                kwargs["queryset"] = target.objects.filter(school=request.user.school)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

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


class SchoolRestrictedInlineMixin:
    """Restrict inline FK/M2M choices to the administrator's own school."""

    def _restricted_queryset(self, db_field, request):
        if request.user.is_superuser or not request.user.school_id:
            return None
        target = db_field.remote_field.model
        if target is School:
            return School.objects.filter(pk=request.user.school_id)
        if hasattr(target, "school"):
            return target.objects.filter(school=request.user.school)
        return None

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        queryset = self._restricted_queryset(db_field, request)
        if queryset is not None:
            kwargs["queryset"] = queryset
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        queryset = self._restricted_queryset(db_field, request)
        if queryset is not None:
            kwargs["queryset"] = queryset
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class PlatformOnlyModelAdmin(admin.ModelAdmin):
    """Admin restricted to platform superusers (e.g. School records)."""

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


@admin.register(AuditEvent)
class AuditEventAdmin(PlatformOnlyModelAdmin):
    """Read-only governance trail: superusers review, nobody edits.

    Add/change/delete are all disabled so the trail stays append-only even
    for the platform superuser (AGENTS.md section 6).
    """

    list_display = ("created_at", "actor", "action", "target_type", "target_id")
    list_filter = ("action", "created_at")
    search_fields = ("actor__username", "target_id", "detail")
    readonly_fields = ("actor", "action", "target_type", "target_id", "detail", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False