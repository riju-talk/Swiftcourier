from decimal import Decimal

from django.conf import settings
from django.db import models

from account.models import MyModel
from order_manager.models import Order


SMS_STATUS_CHOICES = (
    ("ready_to_ship", "Order Created"),
    ("pending_pickup", "Shipped"),
    ("in_transit", "In Transit"),
    ("out_for_delivery", "Out For Delivery"),
    ("delivered", "Delivered"),
    ("ndr", "NDR"),
    ("cancelled", "Cancelled"),
)


class SMSSettings(MyModel):
    PROVIDERS = (
        ("twilio", "Twilio"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_settings",
    )
    enabled = models.BooleanField(default=False)
    provider = models.CharField(max_length=20, choices=PROVIDERS, default="twilio")
    default_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.50")
    )
    default_country_code = models.CharField(max_length=8, default="+91")
    opt_in_required = models.BooleanField(default=True)
    monthly_cap = models.PositiveIntegerField(
        default=0,
        help_text="0 means no cap",
    )

    def __str__(self) -> str:
        return f"SMSSettings({self.user.email})"


class SMSTemplate(MyModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_templates",
    )
    status = models.CharField(max_length=50, choices=SMS_STATUS_CHOICES)
    language = models.CharField(max_length=12, default="en")
    content = models.TextField(default="")
    is_active = models.BooleanField(default=True)
    provider_template_id = models.CharField(max_length=120, blank=True, default="")
    version = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("user", "status", "version")

    def __str__(self) -> str:
        return f"SMSTemplate({self.user.email}, {self.status}, v{self.version})"


class SMSStatusConfig(MyModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_status_configs",
    )
    status = models.CharField(max_length=50, choices=SMS_STATUS_CHOICES)
    enabled = models.BooleanField(default=True)
    template = models.ForeignKey(
        SMSTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_configs",
    )
    cost_per_message = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.50")
    )

    class Meta:
        unique_together = ("user", "status")

    def __str__(self) -> str:
        return f"SMSStatusConfig({self.user.email}, {self.status})"


class SMSNotificationLog(MyModel):
    SEND_STATUS = (
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    )

    DELIVERY_STATUS = (
        ("unknown", "Unknown"),
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("undelivered", "Undelivered"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_logs",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_logs",
    )
    status = models.CharField(max_length=50, choices=SMS_STATUS_CHOICES)
    template_version = models.PositiveIntegerField(default=1)
    to_number = models.CharField(max_length=32, default="")
    message = models.TextField(default="")
    provider = models.CharField(max_length=20, blank=True, default="")
    provider_message_id = models.CharField(max_length=120, blank=True, default="")
    send_status = models.CharField(max_length=20, choices=SEND_STATUS, default="pending")
    delivery_status = models.CharField(
        max_length=20, choices=DELIVERY_STATUS, default="unknown"
    )
    charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    api_response = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("order", "status")
        indexes = [
            models.Index(fields=["user", "created_at"], name="sms_integ_user_created_idx"),
            models.Index(fields=["provider_message_id"], name="sms_integ_provider_msg_idx"),
        ]

    def __str__(self) -> str:
        return f"SMSNotificationLog({self.user.email}, {self.status}, {self.send_status})"
