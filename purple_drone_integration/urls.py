from django.urls import path
from . import views


app_name = "purpledrone_integration"


urlpatterns = [
    path("webhook/", views.webhook, name="webhook")
]
