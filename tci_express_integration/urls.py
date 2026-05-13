from django.urls import path
from . import views

app_name = "tci_express_integration"

urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
]
