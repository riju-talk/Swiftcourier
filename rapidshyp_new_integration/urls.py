from django.urls import path
from . import views

app_name = "rapidshyp_new_integration"

urlpatterns = [
    path("webhook/", views.rapidshyp_new_webhook, name="rapidshyp_new_webhook"),
]
