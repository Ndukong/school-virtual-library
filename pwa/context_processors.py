from django.conf import settings


def pwa_enabled(request):
    return {"PWA_ENABLED": getattr(settings, "PWA_ENABLED", True)}