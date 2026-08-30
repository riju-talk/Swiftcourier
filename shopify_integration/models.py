# shopify_integration/models.py

from django.db import models
from account.models import MyModel
from django.db.models import Sum
from django.utils.timezone import localdate
from django.conf import settings


def _default_shopify_api_token():
    """App-wide Shopify API key, used as the per-store default at creation time."""
    return settings.SHOPIFY_API_KEY


def _default_shopify_api_secret():
    """App-wide Shopify API secret, used as the per-store default at creation time."""
    return settings.SHOPIFY_API_SECRET


class ShopifyStore(MyModel):
    user = models.ForeignKey(
        "account.User", on_delete=models.CASCADE, related_name="shopify_stores"
    )
    # In User model, after the woocommerce fields:
    shopify_shop_domain = models.CharField(
        max_length=255,
        verbose_name="Shopify Shop Domain (e.g. mystore.myshopify.com)",
        unique=True,
    )
    shopify_access_token = models.CharField(
        max_length=255, default="", blank=True, verbose_name="Shopify Access Token"
    )
    shopify_webhook_secret = models.CharField(
        max_length=255, default="", blank=True, verbose_name="Shopify Webhook Secret"
    )
    shopify_api_token = models.CharField(
        max_length=100,
        default=_default_shopify_api_token,
    )
    shopify_api_secret = models.CharField(
        max_length=100,
        default=_default_shopify_api_secret,
    )
    shopify_installed_at = models.DateTimeField(
        null=True, blank=True, default=None, verbose_name="Shopify App Installed At"
    )
    shopify_uninstalled_at = models.DateTimeField(
        null=True, blank=True, default=None, verbose_name="Shopify App Uninstalled At"
    )
    default_order_length_cm = models.IntegerField(
        default=10,
    )
    default_order_width_cm = models.IntegerField(
        default=15,
    )
    default_order_height_cm = models.IntegerField(
        default=15,
    )
    is_active = models.BooleanField(default=False)

    @classmethod
    def create_shopify_store(cls, user, shop_url):
        return cls.objects.get_or_create(
            user=user,
            shopify_shop_domain=shop_url,
        )

    @classmethod
    def get_shopify_store_by_shop_url(cls, shop_url):
        return cls.objects.filter(shopify_shop_domain=shop_url).first()

    @classmethod
    def get_user_by_shop_url(cls, shop_url):
        return cls.objects.get(shopify_shop_domain=shop_url).user

    @classmethod
    def get_stores_dashboard_data(cls, user) -> list[dict]:
        from order_manager.models import Order

        stores = cls.objects.filter(user=user, is_active=True).prefetch_related(
            "webhooklogs"
        )

        result = []

        for store in stores:
            today = localdate()

            store_orders = Order.objects.filter(
                user=user,
                channel="shopify",
                order_date__date=today,
            )

            # If you have a FK/field linking Order to ShopifyStore, filter by store too.
            # e.g. store_orders = store_orders.filter(shopify_store=store)

            orders_today = store_orders.count()

            revenue = store_orders.aggregate(total=Sum("total_amount"))["total"] or 0.0

            products = 0  # populate from Shopify API or a local Product count if linked

            aov = round(revenue / orders_today, 2) if orders_today else 0.0

            recent_orders = Order.objects.filter(
                user=user,
                channel="shopify",
            ).order_by("-order_date")[:10]

            orders_data = [
                {
                    "id": f"#{o.order_number or o.id}",
                    "customer": (
                        o.shipping_address.name if o.shipping_address else "N/A"
                    ),
                    "date": o.order_date.strftime("%b %d, %Y"),
                    "amount": f"₹{o.total_amount:.2f}",
                    "payment": getattr(o, "payment", None)
                    and o.payment.method
                    or "N/A",
                    "status": o.status,
                }
                for o in recent_orders
            ]

            result.append(
                {
                    "id": store.id,
                    "name": store.shopify_shop_domain.split(".")[0]
                    .replace("-", " ")
                    .title(),
                    "url": store.shopify_shop_domain,
                    "revenue": round(revenue, 2),
                    "orders_today": orders_today,
                    "products": products,
                    "aov": aov,
                    "orders": orders_data,
                }
            )

        return result


class WebhookLog(MyModel):
    """
    Audit log for every incoming Shopify webhook.

    Purposes:
        - Debugging: inspect raw payloads for any webhook event.
        - Idempotency: detect and skip duplicate webhook deliveries.
        - Tracing: link each webhook to the Order it created.
        - Retry: identify failed webhooks for manual reprocessing.

    Status lifecycle:
        received   → webhook arrived, not yet processed
        processing → processor function has started (set before calling processor)
        processed  → pipeline completed successfully
        duplicate  → same topic + shopify_id already processed; safely skipped
        failed     → pipeline raised an error; see error_message for details

    Fields:
        topic:        Shopify webhook topic string
                      e.g. 'orders/create', 'orders/cancelled'
        shop_domain:  Shopify shop domain
                      e.g. 'mystore.myshopify.com'
        shopify_id:   Shopify resource ID (order ID, product ID, etc.)
                      Stored as string to handle large Shopify IDs safely.
        payload:      Full raw JSON payload received from Shopify.
        status:       One of STATUSES choices above.
        error_message:Populated on failure with exception message.
        linked_order: FK to the Order created from this webhook (if any).
        received_at:  Timestamp of webhook arrival (auto-set, from MyModel.created_at).
    """

    STATUSES = [
        ("received", "Received"),
        ("processing", "Processing"),
        ("processed", "Processed"),
        ("duplicate", "Duplicate"),
        ("failed", "Failed"),
    ]

    topic = models.CharField(max_length=100, db_index=True)
    store = models.ForeignKey(
        ShopifyStore,
        on_delete=models.CASCADE,
        null=True,
        default=None,
        related_name="webhooklogs",
    )
    shopify_id = models.CharField(max_length=100, blank=True, db_index=True)
    payload = models.JSONField()
    status = models.CharField(
        max_length=20,
        choices=STATUSES,
        default="received",
        db_index=True,
    )
    error_message = models.TextField(blank=True)
    linked_order = models.ForeignKey(
        "order_manager.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_logs",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Used in duplicate check: topic + shopify_id + status
            models.Index(
                fields=["topic", "shopify_id", "status"],
                name="webhooklog_dedup_idx",
            ),
        ]

    def __str__(self):
        return f"[{self.topic}] - {self.status} ({self.shopify_id})"
