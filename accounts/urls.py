from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/admin/", views.AdminDashboardView.as_view(), name="dashboard-admin"),
    path("dashboard/teacher/", views.TeacherDashboardView.as_view(), name="dashboard-teacher"),
    path("dashboard/student/", views.StudentDashboardView.as_view(), name="dashboard-student"),
]