from django.urls import path

from learning import views

urlpatterns = [
    path("", views.PracticeHomeView.as_view(), name="practice-home"),
    path("start/", views.QuizStartView.as_view(), name="practice-start"),
    path("exam/start/", views.ExamPracticeStartView.as_view(), name="practice-exam-start"),
    path("attempt/<uuid:public_id>/", views.AttemptPageView.as_view(), name="attempt-page"),
    path("attempt/<uuid:public_id>/submit/", views.AttemptSubmitView.as_view(), name="attempt-submit"),
    path("result/<uuid:public_id>/", views.AttemptResultView.as_view(), name="attempt-result"),
    path("response/<int:pk>/mark/", views.ResponseSelfMarkView.as_view(), name="response-self-mark"),
    path("progress/", views.ProgressView.as_view(), name="practice-progress"),
]