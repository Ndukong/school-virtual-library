from django.urls import path

from api import views

urlpatterns = [
    path("resources/", views.ResourceListApiView.as_view(), name="api-resources"),
    path("search/", views.SearchApiView.as_view(), name="api-search"),
    path("ask/", views.AskApiView.as_view(), name="api-ask"),
    path("answers/<uuid:public_id>/", views.AnswerApiView.as_view(), name="api-answer"),
    path("questions/", views.QuestionListApiView.as_view(), name="api-questions"),
]