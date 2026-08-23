from django.urls import path

from whatsapp import views

urlpatterns = [
    path("webhook/", views.webhook_receive, name="whatsapp-webhook"),
    path("webhook/verify/", views.webhook_verify, name="whatsapp-webhook-verify"),
]