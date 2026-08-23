from django.urls import path

from examinations import views
from examinations.views import exam_print_view

urlpatterns = [
    path("", views.ExamListView.as_view(), name="exam-list"),
    path("new/", views.ExamCreateView.as_view(), name="exam-create"),
    path("<uuid:public_id>/", views.ExamDetailView.as_view(), name="exam-detail"),
    path("<uuid:public_id>/print/", exam_print_view, kwargs={"with_answers": False}, name="exam-print"),
    path(
        "<uuid:public_id>/print/answers/",
        exam_print_view,
        kwargs={"with_answers": True},
        name="exam-print-answers",
    ),
    path("<uuid:public_id>/<str:action>/", views.ExamActionView.as_view(), name="exam-action"),
]