# admin.py
from django.contrib import admin
from account.admin import MyModelAdmin

from order_manager.models import (
    BulkOrderFile,
    CODRemittance,
    Hub,
    Payment,
    Shipment,
    Address,
    Order,
    OrderItem,
    Product,
    Courier,
)


@admin.register(Hub)
class HubAdmin(MyModelAdmin):
    list_display = ("name", "city", "state", "country", "phone", "address_line1", "address_line2")
    search_fields = ("name", "city", "pin_code", "address_line1", "address_line2", "phone")
    list_filter = ("state", "country")


@admin.register(CODRemittance)
class CODRemittanceAdmin(MyModelAdmin):
    list_display = (
        "id",
        "_user",
        "_status",
        "_generated_cod",
        "_amount_paid",
        "_payout_date",
    )
    list_filter = ("_status", "_user")


@admin.register(BulkOrderFile)
class BulkOrderFileAdmin(MyModelAdmin):
    list_display = ("id", "file", "created_at")


@admin.register(Address)
class AddressAdmin(MyModelAdmin):
    list_display = (
        "user",
        "label",
        "city",
        "state",
        "pin_code",
        "name",
    )
    search_fields = ("user__email", "city", "pin_code")
    list_filter = ("state", "country")


@admin.register(Product)
class ProductAdmin(MyModelAdmin):
    list_display = ("id", "sku", "name", "price", "stock")
    search_fields = ("sku", "name")


@admin.register(OrderItem)
class OrderItemAdmin(MyModelAdmin):
    list_display = ("product", "order", "quantity", "total_price", "sku_code")
    search_fields = ("sku_code",)


@admin.register(Order)
class OrderAdmin(MyModelAdmin):
    list_display = ("id", "user", "status", "total_amount", "placed_at")
    search_fields = ("id", "user__email")
    list_filter = ("status", "channel", "placed_at")


@admin.register(Shipment)
class ShipmentAdmin(MyModelAdmin):
    list_display = ("tracking_number", "status", "order", "courier", "hub")
    search_fields = ("tracking_number", "order__id")
    list_filter = ("status", "courier", "hub")
    readonly_fields = ("shipped_at", "delivered_at")


@admin.register(Payment)
class PaymentAdmin(MyModelAdmin):
    list_display = ("method", "order", "status", "amount")
