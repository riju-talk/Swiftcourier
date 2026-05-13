from django.urls import path
from .views import webhook


app_name = "parcelx_integration"


urlpatterns = [
    path("webhook/", webhook, name="webhook"),
]
