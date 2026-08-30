from django.urls import path

from . import views


app_name = "serviceability"


urlpatterns = [
    path("check-serviceability/", views.check_serviceability, name="check-serviceability"),
    path("warehouses/", views.get_warehouses, name="warehouses"),
    path("dashboard-data/", views.dashboard_data, name="dashboard-data"),
    path("health/", views.health, name="health"),
]
