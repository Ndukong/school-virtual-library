from django.urls import path

from ai import views

urlpatterns = [
    path("ask/", views.AskView.as_view(), name="ai-ask"),
    path("answer/<uuid:public_id>/", views.AnswerView.as_view(), name="ai-answer"),
]