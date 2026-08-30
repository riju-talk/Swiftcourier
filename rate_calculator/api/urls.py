from django.urls import path
from . import views

app_name = "rate_calculator"

urlpatterns = [
    path("calculator/", views.rate_calculator, name="rate-calculator"),
]
