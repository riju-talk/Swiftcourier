from django.urls import path
from . import views

app_name = 'rapidshyp_integration'

urlpatterns = [
    path('webhook/', views.rapidshyp_webhook, name='rapidshyp_webhook'),
]