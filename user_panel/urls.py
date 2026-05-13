from django.urls import path

from . import views


app_name = "user_panel"

urlpatterns = [
    path("statistics/", views.statistics, name="statistics"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("analytics/", views.analytics, name="analytics"),
    path("mis/", views.mis, name="mis"),
    path("order/add-order/", views.add_order, name="add-order"),
    path("order/add-order-new/", views.add_order_new, name="add-order-new"),
    path("order/add-reverse-order/", views.add_reverse_order, name="add-reverse-order"),
    path("order/failed-order/", views.failed_order, name="failed-order"),
    path("order/cancelled-order/", views.cancelled_order, name="cancelled-order"),
    path("order/details/<int:id>/", views.order_details, name="order-details"),
    path(
        "weight-discrepancies/", views.weight_discrepancies, name="weight-discrepancies"
    ),
    path("ndr/", views.ndr, name="ndr"),
    path("shipment/<str:status>/", views.shipment, name="shipment"),
    # path("reports/", views.reports, name="reports"),
    path("finance/invoices/", views.invoices, name="invoices"),
    path("finance/rate-card/", views.rate_card, name="rate-card"),
    path("finance/shipping-charges/", views.shipping_charges, name="shipping-charges"),
    path("finance/cod-remittance/", views.cod_remittance, name="cod-remittance"),
    path("finance/cod-remittance/download-file/<int:cod_remittance_id>/", views.download_cod_remittance_file, name="download-cod-remittance-file"),
    path("finance/all-recharges/", views.all_recharges, name="all-recharges"),
    path("finance/wallet-history/", views.wallet_history, name="wallet-history"),
    path("setting/kyc/", views.kyc, name="kyc"),
    path("setting/label/", views.label, name="label"),
    path("setting/invoice/", views.invoice, name="invoice"),
    path("setting/printer/", views.printer, name="printer"),
    path("setting/courier-rules/", views.courier_rules, name="courier-rules"),
    path("billing/", views.billing, name="billing"),
    path("add-hub/", views.add_hub, name="add-hub"),
    path("all-hub/", views.all_hub, name="all-hub"),
    path("edit-hub/", views.edit_hub, name="edit-hub"),
    path("deactivate-hub/", views.deactivate_hub, name="deactivate-hub"),
    path("make-primary-hub/", views.make_primary_hub, name="make-primary-hub"),
    path("view-label/<int:order_id>/", views.view_label, name="view-label"),
    path("view-invoice/<int:order_id>/", views.view_invoice, name="view-invoice"),
    path("api/labels/", views.labels_api, name="labels-api"),
    path("api/labels/", views.labels_api, name="labels_api"),
    path("api/ats-label-proxy/", views.ats_label_proxy, name="ats-label-proxy"),
    path("download-label/", views.download_label, name="download-label"),
    path("download-label-old/", views.download_label_old, name="download-label-old"),
    path("download-invoice/", views.download_invoice, name="download-invoice"),
    path("get-awb-details/", views.get_awb_details, name="get-awb-details"),
    # integrations
    path("integration/shopify/", views.shopify_integration, name="shopify-integration"),
]
