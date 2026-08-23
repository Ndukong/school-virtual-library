from django.urls import path

from question_bank import views

urlpatterns = [
    path("", views.QuestionListView.as_view(), name="question-list"),
    path("import/", views.ImportOptionsView.as_view(), name="question-import"),
    path("import/run/", views.ImportRunView.as_view(), name="question-import-run"),
    path("new/", views.QuestionCreateView.as_view(), name="question-create"),
    path("<uuid:public_id>/", views.QuestionDetailView.as_view(), name="question-detail"),
    path("<uuid:public_id>/edit/", views.QuestionUpdateView.as_view(), name="question-edit"),
    path("<uuid:public_id>/<str:action>/", views.QuestionActionView.as_view(), name="question-action"),
]