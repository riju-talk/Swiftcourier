from django.urls import path
from . import views

app_name = "wallet"

urlpatterns = [
    path("add-money/", views.add_money, name="add-money"),
    path("checkout/", views.checkout, name="checkout"),
    path("redirect/<str:merchant_txn_id>/", views.payment_redirect, name="redirect"),
    path("callback/", views.callback, name="callback"),
    path("create-razorpay-transaction/", views.create_razorpay_transaction, name="create-razorpay-transaction"),
    path("verify-razorpay-transaction/", views.verify_razorpay_transaction, name="verify-razorpay-transaction"),
]
