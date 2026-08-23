from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import User
from accounts.permissions import is_admin
from students.admin import StudentInline
from teachers.admin import TeacherInline


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "school", "is_staff", "is_active")
    list_filter = ("role", "school", "is_staff", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")

    inlines = [StudentInline, TeacherInline]

    # Fieldsets for platform superusers: full control.
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("School and role", {"fields": ("role", "school")}),
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
        ("Status", {"fields": ("is_active",)}),
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
        if not request.user.is_superuser:
            obj.school = request.user.school
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)

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