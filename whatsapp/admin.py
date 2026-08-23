from django.contrib import admin

from whatsapp.models import WhatsAppLink, WhatsAppMessage, WhatsAppSession


@admin.register(WhatsAppLink)
class WhatsAppLinkAdmin(admin.ModelAdmin):
    list_display = ("code", "user", "expires_at", "used_at")
    search_fields = ("code", "user__username")
    readonly_fields = ("code", "user", "expires_at", "used_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(user__school=request.user.school)
        return qs.none()

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "linked_user", "state", "last_seen_at")
    search_fields = ("phone_number", "linked_user__username")
    readonly_fields = ("phone_number", "linked_user", "state", "context", "last_seen_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(linked_user__school=request.user.school)
        return qs.none()

    def has_add_permission(self, request):
        return False


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ("direction", "phone_number", "user", "body", "created_at", "handled_ok")
    list_filter = ("direction",)
    search_fields = ("phone_number", "user__username", "body")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.school_id:
            return qs.filter(user__school=request.user.school)
        return qs.none()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False