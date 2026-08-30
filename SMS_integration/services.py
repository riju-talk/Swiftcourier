import logging
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from account.models import Notification
from order_manager.models import Order
from wallet.models import Transaction as WalletTransaction

from .models import (
    SMS_STATUS_CHOICES,
    SMSNotificationLog,
    SMSSettings,
    SMSStatusConfig,
    SMSTemplate,
)
from .providers import get_provider


logger = logging.getLogger("my-logger")


DEFAULT_STATUS_CONFIGS = [
    {
        "status": "ready_to_ship",
        "label": "Order Created",
        "template": (
            "Hi {customer_name}, your order #{order_id} has been created successfully. "
            "We will update you once it is shipped."
        ),
    },
    {
        "status": "pending_pickup",
        "label": "Shipped",
        "template": (
            "Good news! Your order #{order_id} has been shipped via {courier_name}. "
            "Track here: {tracking_link}"
        ),
    },
    {
        "status": "in_transit",
        "label": "In Transit",
        "template": (
            "Your order #{order_id} is currently in transit and on its way to you."
        ),
    },
    {
        "status": "out_for_delivery",
        "label": "Out for Delivery",
        "template": "Your order #{order_id} is out for delivery today.",
    },
    {
        "status": "delivered",
        "label": "Delivered",
        "template": (
            "Your order #{order_id} has been delivered successfully. "
            "Thank you for shopping with us!"
        ),
    },
    {
        "status": "ndr",
        "label": "NDR",
        "template": (
            "Delivery attempt failed for order #{order_id}. "
            "Please contact support or update your delivery details."
        ),
    },
    {
        "status": "cancelled",
        "label": "Cancelled",
        "template": "Your order #{order_id} has been cancelled.",
    },
]


SAMPLE_CONTEXT = {
    "customer_name": "Rahul",
    "order_id": "SZ12345",
    "awb_number": "AWB123456789",
    "courier_name": "Shipzee",
    "tracking_link": "https://track.shipzee.tech/awb/AWB123456789",
    "estimated_delivery_date": "2026-05-25",
}


def get_supported_statuses() -> list[str]:
    return [item[0] for item in SMS_STATUS_CHOICES]


def get_status_label(status: str) -> str:
    for item in DEFAULT_STATUS_CONFIGS:
        if item["status"] == status:
            return item["label"]
    for key, label in SMS_STATUS_CHOICES:
        if key == status:
            return label
    return status


def ensure_sms_defaults(user) -> SMSSettings:
    settings_obj, _ = SMSSettings.objects.get_or_create(user=user)

    for item in DEFAULT_STATUS_CONFIGS:
        template_obj, _ = SMSTemplate.objects.get_or_create(
            user=user,
            status=item["status"],
            version=1,
            defaults={
                "content": item["template"],
                "is_active": True,
            },
        )
        config_obj, created = SMSStatusConfig.objects.get_or_create(
            user=user,
            status=item["status"],
            defaults={
                "enabled": True,
                "template": template_obj,
                "cost_per_message": settings_obj.default_rate,
            },
        )
        if not created and config_obj.template is None:
            config_obj.template = template_obj
            config_obj.save(update_fields=["template", "updated_at"])

    return settings_obj


def normalize_phone(raw: str, country_code: str) -> str:
    if not raw:
        return ""
    stripped = raw.strip()
    if stripped.startswith("+"):
        return stripped

    digits = re.sub(r"\D", "", stripped)
    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) == 10:
        cc = country_code.strip() or "+91"
        if not cc.startswith("+"):
            cc = f"+{cc}"
        return f"{cc}{digits}"

    if len(digits) >= 11:
        return f"+{digits}"

    return ""


def render_template(template: str, context: dict[str, str]) -> str:
    def replace(match):
        key = match.group(1)
        return str(context.get(key, ""))

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", replace, template or "")


def build_message_context(order: Order) -> dict[str, str]:
    shipping = getattr(order, "shipping_address", None)
    shipment = getattr(order, "shipment", None)
    courier = getattr(order, "logistic_partner", None)

    customer_name = ""
    if shipping and getattr(shipping, "name", ""):
        customer_name = shipping.name
    elif shipping and getattr(shipping, "company_name", ""):
        customer_name = shipping.company_name
    elif getattr(order.user, "full_name", ""):
        customer_name = order.user.full_name

    tracking_link = ""
    if courier and getattr(order, "awb_number", ""):
        try:
            tracking_link = courier.get_tracking_url(order.awb_number)
        except Exception:
            tracking_link = ""

    estimated_delivery = ""
    if shipment and shipment.expected_delivery:
        try:
            estimated_delivery = shipment.expected_delivery.strftime("%Y-%m-%d")
        except Exception:
            estimated_delivery = ""

    return {
        "customer_name": customer_name,
        "order_id": order.get_order_id_for_aggregator(),
        "awb_number": order.awb_number or "",
        "courier_name": courier.name if courier else "",
        "tracking_link": tracking_link,
        "estimated_delivery_date": estimated_delivery,
    }


def parse_decimal(value: str, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return default


def _month_start() -> date:
    today = timezone.localdate()
    return today.replace(day=1)


def _monthly_sent_count(user) -> int:
    return SMSNotificationLog.objects.filter(
        user=user,
        send_status="sent",
        created_at__date__gte=_month_start(),
    ).count()


def process_notification(
    order: Order,
    status: str,
    old_status: str | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    if old_status and old_status == status:
        return False, "status_unchanged"

    settings_obj = ensure_sms_defaults(order.user)
    config = SMSStatusConfig.objects.filter(
        user=order.user,
        status=status,
    ).select_related("template").first()

    if not config:
        return False, "config_missing"

    existing_log = SMSNotificationLog.objects.filter(
        order=order,
        status=status,
    ).first()

    if existing_log and existing_log.send_status in {"sent", "pending"} and not force:
        return False, "duplicate"

    if existing_log and existing_log.send_status in {"failed", "skipped"} and not force:
        return False, "previously_failed"

    if not settings_obj.enabled or not config.enabled:
        log = existing_log or SMSNotificationLog.objects.create(
            user=order.user,
            order=order,
            status=status,
            template_version=(config.template.version if config.template else 1),
        )
        log.send_status = "skipped"
        log.error_message = "SMS notifications disabled"
        log.save(update_fields=["send_status", "error_message", "updated_at"])
        return False, "disabled"

    if settings_obj.monthly_cap and _monthly_sent_count(order.user) >= settings_obj.monthly_cap:
        log = existing_log or SMSNotificationLog.objects.create(
            user=order.user,
            order=order,
            status=status,
            template_version=(config.template.version if config.template else 1),
        )
        log.send_status = "skipped"
        log.error_message = "Monthly cap reached"
        log.save(update_fields=["send_status", "error_message", "updated_at"])
        return False, "cap_reached"

    template = config.template
    if template is None or not template.is_active:
        log = existing_log or SMSNotificationLog.objects.create(
            user=order.user,
            order=order,
            status=status,
            template_version=(template.version if template else 1),
        )
        log.send_status = "failed"
        log.error_message = "Template missing or inactive"
        log.save(update_fields=["send_status", "error_message", "updated_at"])
        return False, "template_missing"

    context = build_message_context(order)
    message = render_template(template.content, context)

    raw_phone = ""
    if getattr(order, "shipping_address", None):
        raw_phone = order.shipping_address.phone or order.shipping_address.alt_phone

    to_number = normalize_phone(raw_phone, settings_obj.default_country_code)
    if not to_number:
        log = existing_log or SMSNotificationLog.objects.create(
            user=order.user,
            order=order,
            status=status,
            template_version=template.version,
        )
        log.send_status = "failed"
        log.error_message = "Missing or invalid phone number"
        log.save(update_fields=["send_status", "error_message", "updated_at"])
        return False, "invalid_phone"

    cost = (
        config.cost_per_message
        if config.cost_per_message is not None
        else settings_obj.default_rate
    )
    if not order.user.have_balance(float(cost)):
        log = existing_log or SMSNotificationLog.objects.create(
            user=order.user,
            order=order,
            status=status,
            template_version=template.version,
            to_number=to_number,
            message=message,
        )
        log.send_status = "skipped"
        log.error_message = "Insufficient wallet balance"
        log.save(update_fields=["send_status", "error_message", "updated_at"])
        return False, "insufficient_balance"

    log = existing_log
    if not log:
        log = SMSNotificationLog.objects.create(
            user=order.user,
            order=order,
            status=status,
            template_version=template.version,
            to_number=to_number,
            message=message,
            provider=settings_obj.provider,
            send_status="pending",
        )

    provider = get_provider(settings_obj)
    response = provider.send_message(to_number=to_number, body=message)

    if not response.success:
        log.send_status = "failed"
        log.error_message = response.error or "Provider send failed"
        log.api_response = {"provider": response.raw}
        log.save(update_fields=["send_status", "error_message", "api_response", "updated_at"])
        return False, "provider_failed"

    log.provider_message_id = response.message_id
    log.delivery_status = response.status or "sent"
    log.api_response = {"provider": response.raw}
    log.sent_at = timezone.now()

    trxn = WalletTransaction.create_transaction(
        user=order.user,
        merchant_txn_id=f"sms_{order.id}_{status}_{uuid.uuid4()}",
        amount_rs=float(cost),
        desc="other",
        transaction_type="debit",
        json={"type": "sms", "status": status},
        other_reason="SMS notification charge",
    )

    debited = trxn.debit()
    if debited:
        log.charge = cost
        log.send_status = "sent"
    else:
        log.send_status = "sent"
        log.error_message = "Wallet debit failed after send"
        Notification.objects.create(
            user=order.user,
            category="warning",
            msg="SMS notification sent but wallet debit failed. Please contact support.",
        )

    log.save(
        update_fields=[
            "provider_message_id",
            "delivery_status",
            "sent_at",
            "charge",
            "send_status",
            "error_message",
            "updated_at",
        ]
    )

    return True, "sent"
