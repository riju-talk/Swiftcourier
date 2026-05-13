from django.urls import path
from . import views


app_name = "xpressbees_integration"


urlpatterns = [
    path('webhook/', views.webhook, name='webhook'),
]
