from django.urls import path

from . import views

app_name = "sms_integration"

urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
]
