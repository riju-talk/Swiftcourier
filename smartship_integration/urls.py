from django.urls import path
from .views import webhook


app_name = "smartship_integration"


urlpatterns = [
    path("webhook/", webhook, name="webhook"),
]
