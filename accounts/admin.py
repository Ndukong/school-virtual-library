from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import LoginFailure, LoginLock, PasswordReset, User
from accounts.permissions import is_admin
from accounts.services import reset_user_locks
from common.audit import record as audit_record
from students.admin import StudentInline
from teachers.admin import TeacherInline


@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ("admin_user", "target_user", "created_at", "completed_at")
    search_fields = ("target_user__username", "admin_user__username")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(target_user__school=request.user.school)
        return qs.none()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.action(description="Unlock login for selected users")
def unlock_login(modeladmin, request, queryset):
    for user in queryset:
        reset_user_locks(user.username)


@admin.register(LoginLock)
class LoginLockAdmin(admin.ModelAdmin):
    list_display = ("username", "ip", "attempts", "locked_until", "updated_at")
    search_fields = ("username", "ip")
    readonly_fields = ("username", "ip", "attempts", "locked_until", "updated_at")
    actions = [unlock_login]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LoginFailure)
class LoginFailureAdmin(admin.ModelAdmin):
    list_display = ("username", "ip", "created_at")
    search_fields = ("username", "ip")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "school", "is_staff", "is_active", "must_change_password")
    list_filter = ("role", "school", "is_staff", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")

    inlines = [StudentInline, TeacherInline]

    # Fieldsets for platform superusers: full control.
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("School and role", {"fields": ("role", "school", "must_change_password")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "role", "school"),
            },
        ),
    )

    # Fieldsets for school administrators: they manage people within their
    # own school but can never grant staff/superuser status or edit groups.
    school_admin_fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("School and role", {"fields": ("role",)}),
        ("Status", {"fields": ("is_active", "must_change_password")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    school_admin_add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "role"),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(school=request.user.school)
        return qs.none()

    def get_fieldsets(self, request, obj=None):
        if not request.user.is_superuser:
            return self.school_admin_fieldsets if obj else self.school_admin_add_fieldsets
        return super().get_fieldsets(request, obj)

    def save_model(self, request, obj, form, change):
        # Snapshot the previous state BEFORE the save so role/status changes
        # are audited (governance trail, AGENTS section 6).
        previous = User.objects.filter(pk=obj.pk).first() if change else None
        before = {
            field: getattr(previous, field) if previous else None
            for field in ("role", "school_id", "is_active", "is_staff", "is_superuser", "must_change_password")
        }
        if not request.user.is_superuser:
            obj.school = request.user.school
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)

        if not change:
            audit_record(
                actor=request.user,
                action="user.admin_add",
                target_type="User",
                target_id=obj.username,
                detail=f"role={obj.role} school={obj.school_id}",
            )
            return
        changes = []
        for field in ("role", "school_id", "is_active", "is_staff", "is_superuser", "must_change_password"):
            value = getattr(obj, field)
            if before[field] != value:
                changes.append(f"{field}:{before[field]}->{value}")
        if changes:
            audit_record(
                actor=request.user,
                action="user.admin_change",
                target_type="User",
                target_id=obj.username,
                detail="; ".join(changes),
            )

    def delete_model(self, request, obj):
        audit_record(
            actor=request.user,
            action="user.admin_delete",
            target_type="User",
            target_id=obj.username,
            detail=f"role={obj.role} school={obj.school_id}",
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        rows = list(queryset.values_list("username", "role", "school_id"))
        super().delete_queryset(request, queryset)
        for username, role, school_id in rows:
            audit_record(
                actor=request.user,
                action="user.admin_delete",
                target_type="User",
                target_id=username,
                detail=f"role={role} school={school_id}",
            )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from schools.models import School

        if not request.user.is_superuser and db_field.name == "school" and request.user.school_id:
            kwargs["queryset"] = School.objects.filter(pk=request.user.school_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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