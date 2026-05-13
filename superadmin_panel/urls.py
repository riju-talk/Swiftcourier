from django.urls import path
from . import views

app_name = "superadmin_panel"

urlpatterns = [
    path("statistics/", views.statistics, name="statistics"),
    path("dashboard/overview/", views.dashboard, name="dashboard"),
    path("dashboard/client/", views.dashboard_client, name="dashboard-client"),
    path("dashboard/courier-partner/", views.dashboard_courier_partner, name="dashboard-courier-partner"),
    path("dashboard/courier-performance/", views.dashboard_courier_performance, name="dashboard-courier-performance"),
    path("dashboard/data/", views.dashboard_data, name="dashboard-data"),
    path("add-admin/", views.add_admin, name="add-admin"),
    path("list-admin/", views.list_admin, name="list-admin"),
    path("api-integration/", views.api_integration, name="api-integration"),
    path("user-details/<int:user_id>/", views.user_details, name="user-details"),
    path("all-client/", views.all_clients, name="all-client"),
    path("rate-card/", views.rate_card, name="rate-card"),
    path(
        "view-rate-cards/<int:user_id>/", views.view_rate_cards, name="view-rate-cards"
    ),
    path(
        "edit-rate-card/<int:rate_card_id>/",
        views.edit_rate_card,
        name="edit-rate-card",
    ),
    path(
        "delete-rate-card/<int:rate_card_id>/",
        views.delete_rate_card,
        name="delete-rate-card",
    ),
    path(
        "assign-courier-and-rates/<int:user_id>/",
        views.assign_courier_and_rates,
        name="assign-courier-and-rates",
    ),
    # path("assign-rate-card/", assign_rate_card, name="assign-rate-card"),
    path("assign-commission/", views.assign_commission, name="assign-commission"),
    path("assign-admin/", views.assign_admin, name="assign-admin"),

    path("manage-wallet/<int:user_id>/", views.manage_wallet, name="manage-wallet"),
    path("add-balance/<int:user_id>/", views.add_balance, name="add-balance"),
    path("deduct-balance/<int:user_id>/", views.deduct_balance, name="deduct-balance"),
    path("set-min-balance/", views.set_min_balance, name="set_min_balance"),
    path("set-debit-limit/<int:user_id>/", views.set_debit_limit, name="set-debit-limit"),

    path("get-users/", views.get_users, name="get_users"),
    path("send-notification/", views.send_notification, name="send_notification"),
    # pincode manage
    path("manage-pincode/", views.manage_pincode, name="manage_pincode"),
    path("block-pincodes/", views.block_pincodes, name="block_pincodes"),
    path("unblock-pincodes/", views.unblock_pincodes, name="unblock_pincodes"),
    path("change-client-status/<int:client_id>/", views.change_client_status, name="change_client_status"),
]
