from django.urls import path
from . import views


app_name = "jiffy_integration"


urlpatterns = [
    path("webhook/", views.webhook, name="webhook")
]
