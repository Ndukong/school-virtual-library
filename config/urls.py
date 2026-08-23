"""
URL configuration for the School Virtual Library project.

Authentication and dashboard routes live in the accounts app; the Django
admin remains mounted at /admin/.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
]