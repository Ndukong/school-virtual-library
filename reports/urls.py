from django.urls import path

from reports import views

urlpatterns = [
    path("", views.ReportHubView.as_view(), name="reports-home"),
    path("library/", views.LibraryReportView.as_view(), name="reports-library"),
    path("ai/", views.AIReportView.as_view(), name="reports-ai"),
    path("practice/", views.PracticeReportView.as_view(), name="reports-practice"),
    path("teachers/", views.TeachersReportView.as_view(), name="reports-teachers"),
]