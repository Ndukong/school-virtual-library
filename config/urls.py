"""
URL configuration for the School Virtual Library project.

Auth and dashboards live in the accounts app at the root; the Django admin
remains mounted at /admin/. Media files are intentionally NOT routed here:
documents are only accessible through controlled library views.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("questions/", include("question_bank.urls")),
    path("library/", include("library.urls")),
    path("search/", include("search.urls")),
    path("ai/", include("ai.urls")),
    path("", include("accounts.urls")),
]