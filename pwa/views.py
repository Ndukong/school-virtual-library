"""PWA endpoints: manifest, service worker (root scope), offline shell."""

import json

from django.http import FileResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET

PWA_ROOT = "pwa/"


def _static_path(name):
    from django.contrib.staticfiles import finders

    return finders.find(name)


@require_GET
def manifest_view(request):
    manifest = {
        "name": "School Virtual Library",
        "short_name": "School Library",
        "description": "Approved school learning resources, AI tutoring, and practice.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f4f6f8",
        "theme_color": "#0b5fa5",
        "lang": "en",
        "icons": [
            {
                "src": request.build_absolute_uri("/static/pwa/icons/icon.svg"),
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": request.build_absolute_uri("/static/pwa/icons/icon-maskable.svg"),
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "maskable",
            },
        ],
    }
    return HttpResponse(json.dumps(manifest, indent=2), content_type="application/manifest+json")


@require_GET
def service_worker_view(request):
    """Serve sw.js with a root scope so it can control the whole app.

    The worker MUST NOT be cached: a stale worker is a stale cache policy.
    """
    path = _static_path(f"{PWA_ROOT}sw.js")
    if path is None:
        return HttpResponse(status=404)
    response = FileResponse(open(path, "rb"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def offline_view(request):
    html = render_to_string("pwa/offline.html", {"request": request})
    return HttpResponse(html)