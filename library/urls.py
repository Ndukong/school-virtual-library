from django.urls import path

from library import views

urlpatterns = [
    path("", views.ResourceListView.as_view(), name="library-list"),
    path("upload/", views.ResourceUploadView.as_view(), name="library-upload"),
    path("<uuid:public_id>/", views.ResourceDetailView.as_view(), name="library-detail"),
    path("<uuid:public_id>/download/", views.ResourceDownloadView.as_view(), name="library-download"),
    path("<uuid:public_id>/read/", views.ResourceReadView.as_view(), name="library-read"),
    path("<uuid:public_id>/stream/", views.ResourceStreamView.as_view(), name="library-stream"),
]