from django.urls import path

from pwa import views

urlpatterns = [
    path("manifest.webmanifest", views.manifest_view, name="pwa-manifest"),
    path("sw.js", views.service_worker_view, name="pwa-sw"),
    path("offline/", views.offline_view, name="pwa-offline"),
]