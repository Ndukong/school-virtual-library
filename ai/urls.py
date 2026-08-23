from django.urls import path

from ai import views

urlpatterns = [
    path("ask/", views.AskView.as_view(), name="ai-ask"),
    path("answer/<uuid:public_id>/", views.AnswerView.as_view(), name="ai-answer"),
    path("study/", views.StudyToolView.as_view(), name="ai-study"),
    path("study/mine/", views.MyMaterialsView.as_view(), name="ai-study-mine"),
    path("material/<uuid:public_id>/", views.StudyResultView.as_view(), name="ai-study-result"),
]