from django.contrib import admin
from account.admin import MyModelAdmin
from .models import ShopifyStore, WebhookLog


# Register your models here.
@admin.register(WebhookLog)
class WebhookLogAdmin(MyModelAdmin):
    list_display = (
        "id",
        "shopify_id",
        "status",
    )
    exclude = ("linked_order",)

@admin.register(ShopifyStore)
class ShopifyStoreAdmin(MyModelAdmin):
    list_display = (
        "id",
        "shopify_shop_domain",
        "is_active",
    )
