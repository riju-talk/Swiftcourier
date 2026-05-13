# shopify_integration/urls.py

from django.urls import path
from . import views


app_name = "shopify"


urlpatterns = [
    # ── OAuth ─────────────────────────────────────────────────────────────
    path("auth/install/", views.oauth_install, name="install"),
    path("auth/callback/", views.oauth_callback, name="callback"),
    path("auth/uninstall/", views.oauth_uninstall, name="uninstall"),
    # ── PDF Spec endpoints (Shopify developer's format) ───────────────────
    path("auth/", views.oauth_install, name="auth"),  # PDF: /auth
    path(
        "fetch-orders/", views.fetch_orders, name="fetch_orders"
    ),  # PDF: /fetch-orders
    path("dashboard/", views.dashboard, name="dashboard"),  # PDF: /dashboard
    path(
        "webhook/orders/", views.webhook_orders, name="webhook_orders"
    ),  # PDF: /webhook/orders
    path(
        "webhook/uninstall/", views.oauth_uninstall, name="webhook_uninstall"
    ),  # PDF: /webhook/uninstall
    # ── Granular Shopify webhook routes (raw Shopify format) ──────────────
    path("webhooks/orders/created/", views.webhook_order_created, name="order_created"),
    path("webhooks/orders/updated/", views.webhook_order_updated, name="order_updated"),
    path(
        "webhooks/orders/cancelled/",
        views.webhook_order_cancelled,
        name="order_cancelled",
    ),
    path("webhooks/orders/paid/", views.webhook_order_paid, name="order_paid"),
    # ── Internal dashboard / management APIs ──────────────────────────────
    path("merchants/", views.merchant_list, name="merchant_list"),
    path("merchants/<int:pk>/sync/", views.sync_orders, name="sync_orders"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<str:shopify_id>/", views.order_detail, name="order_detail"),
]
