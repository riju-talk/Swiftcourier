from django.urls import path

from admin_panel.views import dashboard, all_users, user_details

app_name = "admin_panel"

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("all-users/", all_users, name="all-users"),
    path("user/demo/", user_details, name="user-details"),
]
