from django.urls import path
from . import views


app_name = "order_manager"


urlpatterns = [
    path("save/single-order/", views.save_single_order, name="save-single-order"),
    path("save/bulk-order/", views.save_bulk_order, name="save-bulk-order"),
    path("ship-order/", views.ship_order, name="ship-order"),
    path("cancel-order/<int:order_id>/", views.cancel_order, name="cancel-order"),
    path("cancel-bulk-order/", views.cancel_bulk_order, name="cancel-bulk-order"),
    path(
        "download-failed-bulk-orders/<str:download_key>/",
        views.download_failed_bulk_orders,
        name="download-failed-bulk-orders",
    ),
    path(
        "order-edit-clone/<int:order_id>/<str:action>/",
        views.order_edit_clone,
        name="order-edit-clone",
    ),
    path("download-manifest/", views.download_manifest, name="download-manifest"),
    path("wordpress/order-created/<str:user_id>/", views.wordpress_order_created_webhook, name="wordpress-order-created"),
]
