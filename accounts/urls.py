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
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("logout-all/", views.LogoutAllDevicesView.as_view(), name="logout-all"),
    path("reset-password/", views.ResetPasswordListView.as_view(), name="password-reset-list"),
    path("reset-password/run/", views.ResetPasswordRunView.as_view(), name="password-reset-run"),
    path("reset-password/slip/", views.ResetPasswordSlipView.as_view(), name="password-reset-slip"),
    path("password/change/", views.ForcePasswordChangeView.as_view(), name="force-password-change"),
    path("language/", views.SetLanguageView.as_view(), name="set-language"),
]