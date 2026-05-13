# shopify_integration/utils/webhook_processor.py

import logging
import uuid

from django.db import transaction
from django.http import JsonResponse
from django.utils.timezone import now

from account.models import Notification
from order_manager.models import Order, Shipment, Payment
from wallet.models import Transaction as WalletTransaction

from ..models import ShopifyStore, WebhookLog
from ..services.shopify_client import ShopifyClient, ShopifyAPIError
from ..services.courier_service import CourierService, CourierServiceError
from ..validators.order_validators import (
    ShopifyOrderValidationError,
    run_all_create_validations,
    validate_developer_payload,
    validate_not_duplicate,
    validate_has_hub,
    validate_order_cancellable,
    validate_order_updatable,
)
from .parsers import (
    # raw Shopify format
    is_cod,
    get_total_amount,
    total_weight_kg,
    parse_shipping_address,
    parse_line_items,
    update_address_from_shopify,
    # developer custom format
    parse_developer_shipping_address,
    parse_developer_line_items,
    parse_developer_payload_to_standard,
)

logger = logging.getLogger("my-logger")


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _build_merchant_txn_id(order_id, suffix: str) -> str:
    """Generate a unique transaction ID for wallet debit/credit records."""
    return f"shopify_{order_id}_{suffix}_{uuid.uuid4().hex[:8]}"


def _mark_log(log: WebhookLog | None, status: str, error: str = "") -> None:
    """Update WebhookLog status. Safe to call with log=None."""
    if not log:
        return
    log.status = status
    log.error_message = error
    log.save(update_fields=["status", "error_message"])


def _get_shopify_client(user) -> ShopifyClient:
    return ShopifyClient(
        shop_domain=user.shopify_shop_domain,
        access_token=user.shopify_access_token,
    )


def _build_courier_payload(
    order, hub, shipping_address, weight_kg, is_cod_order, total_amount
) -> dict:
    """
    Build the standard courier booking payload from order + hub + address.
    Used by both process_order_created and process_developer_order.
    """
    return {
        "order_id": order.get_order_id_for_aggregator(),
        "pickup": {
            "name": hub.contact_person,
            "phone": hub.phone,
            "address": hub.address_line1,
            "city": hub.city,
            "state": hub.state,
            "pincode": hub.pin_code,
            "country": hub.country,
        },
        "delivery": {
            "name": shipping_address.name,
            "phone": shipping_address.phone,
            "address": shipping_address.line1,
            "address2": shipping_address.line2,
            "city": shipping_address.city,
            "state": shipping_address.state,
            "pincode": shipping_address.pin_code,
            "country": shipping_address.country,
        },
        "weight_kg": weight_kg,
        "is_cod": is_cod_order,
        "cod_amount": total_amount if is_cod_order else 0.0,
        "invoice_amount": total_amount,
        "channel": "shopify",
    }


def _book_and_update(order, shipment, payment, user, courier_payload, log=None) -> dict:
    """
    Book shipment with courier, update Order/Shipment/Payment, debit wallet,
    and push fulfillment to Shopify.

    Shared by process_order_created and process_developer_order.

    Returns:
        dict with success, order_id, awb, courier keys.
    """
    # ── BOOK COURIER ──────────────────────────────────────────────────────
    try:
        booking = CourierService(user).create_shipment(courier_payload)
    except CourierServiceError as e:
        logger.error(f"[_book_and_update] Courier booking failed: {e}")
        Notification.objects.create(
            user=user,
            msg=(
                f"Shopify order #{order.order_number} saved but courier booking failed. "
                f"Error: {str(e)[:120]}. Please book manually."
            ),
            category="error",
        )
        _mark_log(log, "failed", f"Courier error: {e}")
        return {
            "success": False,
            "error": str(e),
            "step": "courier_booking",
            "order_id": order.id,
        }

    awb = booking.get("awb", "")
    courier_obj = booking.get("courier")
    tracking_url = booking.get("tracking_url", "")
    ship_charge = float(booking.get("charge") or 0.0)
    cod_charge = float(booking.get("cod_charge") or 0.0)

    # ── UPDATE ORDER + SHIPMENT + PAYMENT ─────────────────────────────────
    with transaction.atomic():
        order.awb_number = awb
        order.logistic_partner = courier_obj
        order.status = "processing"
        order.save(
            update_fields=["awb_number", "logistic_partner", "status"],
            generate_barcode=True,
        )

        shipment.tracking_number = awb
        shipment.courier = courier_obj
        shipment.booked_at = now()
        shipment.save()

        payment.shipping_charges = ship_charge
        payment.cod_charges = cod_charge
        payment.amount = round(ship_charge + cod_charge, 2)
        payment.status = "completed"
        payment.price_breakup = booking.get("price_breakup", {})
        payment.save()

        if log:
            log.linked_order = order
            log.save(update_fields=["linked_order"])

    # ── DEBIT WALLET ──────────────────────────────────────────────────────
    if ship_charge > 0:
        txn = WalletTransaction.create_transaction(
            user=user,
            merchant_txn_id=_build_merchant_txn_id(order.id, "shipping"),
            amount_rs=ship_charge,
            desc="shopify_shipping_charge",
            transaction_type="debit",
        )
        if not txn.debit(awb_number=awb):
            logger.warning(
                f"[_book_and_update] Wallet debit failed | "
                f"Order #{order.id} | Charge: ₹{ship_charge}"
            )
            Notification.objects.create(
                user=user,
                msg=(
                    f"Low balance! ₹{ship_charge} could not be debited for "
                    f"Shopify order #{order.order_number}. Please recharge your wallet."
                ),
                category="warning",
            )

    # ── PUSH FULFILLMENT TO SHOPIFY ───────────────────────────────────────
    try:
        client = _get_shopify_client(user)
        client.create_fulfillment(
            order_id=order.order_number,
            tracking_number=awb,
            courier_name=courier_obj.name if courier_obj else "",
            tracking_url=tracking_url,
        )
        logger.info(
            f"[_book_and_update] Fulfillment pushed | "
            f"AWB={awb} | Shopify order={order.order_number}"
        )
    except ShopifyAPIError as e:
        # Non-fatal — AWB is saved, Shopify UI just won't show tracking yet
        logger.warning(f"[_book_and_update] Fulfillment push failed: {e}")
        Notification.objects.create(
            user=user,
            msg=(
                f"Order #{order.order_number} booked (AWB: {awb}) but "
                "tracking could not be sent to Shopify. "
                "Please update manually from the Shopify dashboard."
            ),
            category="warning",
        )

    _mark_log(log, "processed")
    logger.info(f"[_book_and_update] DONE | Order #{order.id} | AWB={awb}")
    return {
        "success": True,
        "order_id": order.id,
        "awb": awb,
        "courier": courier_obj.name if courier_obj else "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS ORDER CREATED  (raw Shopify webhook format)
# ─────────────────────────────────────────────────────────────────────────────


def process_order_created(
    user_id: int,
    shopify_order_id: str,
    payload: dict,
    log: WebhookLog | None = None,
    store: ShopifyStore | None = None,
) -> dict:
    """
    Full pipeline for a new order from a raw Shopify webhook payload.

    Called directly from views.py (no background tasks).

    Raw Shopify payload key mapping used here:
        payload['id']                    → shopify_order_id
        payload['shipping_address']      → Address (keys: address1, province, zip)
        payload['line_items']            → Products + OrderItems (keys: grams, variant_id)
        payload['total_price']           → Order.total_amount
        payload['payment_gateway']       → is_cod detection
        payload['note']                  → Order.notes
        payload['checkout_id']           → Payment.transaction_id

    Steps:
        1.  run_all_create_validations (user, duplicate, hub, address)
        2.  Parse weight, COD, total from payload
        3.  Create Address, Order, OrderItems, Shipment, Payment in one transaction
        4.  Book courier, update records, debit wallet, push fulfillment to Shopify

    Returns:
        dict with keys: success, order_id, awb, courier  (or error, step on failure)
    """
    logger.info(
        f"[process_order_created] START | "
        f"user_id={user_id} shopify_order_id={shopify_order_id}"
    )

    # ── STEP 1: VALIDATE ──────────────────────────────────────────────────
    try:
        user, address_dict = run_all_create_validations(
            user_id, shopify_order_id, payload
        )
    except ShopifyOrderValidationError as e:
        logger.warning(f"[process_order_created] Validation failed: {e}")
        _mark_log(log, "failed", str(e))
        return {"success": False, "error": str(e), "step": "validation"}

    # ── STEP 2: PARSE PAYLOAD ─────────────────────────────────────────────
    order_is_cod = is_cod(payload)
    total_amount = get_total_amount(payload)
    weight_kg = total_weight_kg(payload.get("line_items", []))
    line_items = payload.get("line_items", [])

    # ── STEP 3: CREATE DB RECORDS ─────────────────────────────────────────
    try:
        with transaction.atomic():
            shipping_address = parse_shipping_address(address_dict, user)
            shipping_address.save()

            order = Order.objects.create(
                user=user,
                order_number=shopify_order_id,
                channel="shopify",
                status="ready_to_ship",
                shipping_address=shipping_address,
                billing_address=shipping_address,
                total_amount=total_amount,
                invoice_amount=total_amount,
                json=payload,
            )

            if line_items:
                parse_line_items(line_items, order)

            shipment = Shipment.objects.create(
                order=order,
                courier=None,
                tracking_number="",
                status="booked",
                package_weight_kg=weight_kg,
                package_length_cm = store.default_order_length_cm,
                package_width_cm = store.default_order_width_cm,
                package_height_cm = store.default_order_height_cm,
            )

            payment = Payment.objects.create(
                order=order,
                method="cod" if order_is_cod else "prepaid",
                status="pending",
                amount=total_amount,
                cod_collectable_amount=total_amount if order_is_cod else 0.0,
                transaction_id=str(payload.get("checkout_id") or ""),
            )

    except Exception as e:
        logger.exception(f"[process_order_created] DB creation failed: {e}")
        _mark_log(log, "failed", f"DB error: {e}")
        return {"success": False, "error": str(e), "step": "db_creation"}

    logger.info(f"[process_order_created] Order #{order.id} created in DB.")

    # ── STEP 4: BOOK + UPDATE + DEBIT + FULFILL ───────────────────────────
    # courier_payload = _build_courier_payload(
    #     order,
    #     hub,
    #     shipping_address,
    #     weight_kg,
    #     order_is_cod,
    #     total_amount,
    # )
    # return _book_and_update(order, shipment, payment, user, courier_payload, log)


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS ORDER CREATED  (developer custom format — PDF spec)
# ─────────────────────────────────────────────────────────────────────────────


def process_developer_order(
    payload: dict,
    user,
    log: WebhookLog | None = None,
) -> dict:
    """
    Full pipeline for a new order from the Shopify developer's custom payload.

    Developer payload format (PDF spec):
    {
        "order_number":   "#1005",
        "channel":        "shopify",
        "total_amount":   3302.82,
        "invoice_amount": 3302.82,
        "order_date":     "2026-04-23T12:41:59Z",
        "customer":       {"name": "pritam kumar", "email": "..."},
        "shipping_address": {
            "address": "Gurmail nagar lohara...",
            "city":    "Ludhiana",
            "state":   "Punjab",
            "pincode": "141003",
            "country": "India",
            "phone":   "+918210581348"
        },
        "items": [
            {"name": "ATHEN - 32", "quantity": 1, "price": 2799.0}
        ]
    }

    Key differences from raw Shopify format:
        - 'customer'      instead of customer inside shipping_address
        - 'items'         instead of 'line_items'
        - 'pincode'       instead of 'zip'
        - 'address'       instead of 'address1'
        - 'state'         instead of 'province'
        - no 'payment_gateway' → defaults to prepaid
        - no 'grams'      → defaults to 0.5 kg per item

    Steps:
        1.  validate_developer_payload + validate_has_hub + validate_not_duplicate
        2.  Normalize payload
        3.  Create Address, Order, OrderItems, Shipment, Payment in one transaction
        4.  Book courier, update records, debit wallet, push fulfillment to Shopify

    Returns:
        dict with keys: success, order_id, awb, courier  (or error, step on failure)
    """
    shopify_order_id = str(payload.get("order_number") or "")

    logger.info(
        f"[process_developer_order] START | "
        f"order_number={shopify_order_id} user={user.email}"
    )

    # ── STEP 1: VALIDATE ──────────────────────────────────────────────────
    try:
        validate_developer_payload(payload)
        # hub = validate_has_hub(user)
        validate_not_duplicate(shopify_order_id, user)
    except ShopifyOrderValidationError as e:
        logger.warning(f"[process_developer_order] Validation failed: {e}")
        _mark_log(log, "failed", str(e))
        return {"success": False, "error": str(e), "step": "validation"}

    # ── STEP 2: NORMALIZE ─────────────────────────────────────────────────
    normalized = parse_developer_payload_to_standard(payload)
    total_amount = normalized["total_amount"]
    weight_kg = normalized["weight_kg"]
    order_is_cod = normalized["is_cod"]

    # ── STEP 3: CREATE DB RECORDS ─────────────────────────────────────────
    try:
        with transaction.atomic():
            shipping_address = parse_developer_shipping_address(payload, user)
            shipping_address.save()

            order = Order.objects.create(
                user=user,
                order_number=shopify_order_id,
                channel="shopify",
                status="ready_to_ship",
                shipping_address=shipping_address,
                billing_address=shipping_address,
                total_amount=total_amount,
                invoice_amount=normalized["invoice_amount"],
                notes=normalized["notes"],
                awb_number="",
                json=payload,
            )

            parse_developer_line_items(payload, order)

            shipment = Shipment.objects.create(
                order=order,
                courier=None,
                tracking_number="",
                status="booked",
                package_weight_kg=weight_kg,
            )

            payment = Payment.objects.create(
                order=order,
                method="cod" if order_is_cod else "prepaid",
                status="pending",
                amount=total_amount,
                cod_collectable_amount=total_amount if order_is_cod else 0.0,
                transaction_id="",
            )

    except Exception as e:
        logger.exception(f"[process_developer_order] DB creation failed: {e}")
        _mark_log(log, "failed", f"DB error: {e}")
        return {"success": False, "error": str(e), "step": "db_creation"}

    logger.info(f"[process_developer_order] Order #{order.id} created in DB.")

    # ── STEP 4: BOOK + UPDATE + DEBIT + FULFILL ───────────────────────────
    # courier_payload = _build_courier_payload(
    #     order,
    #     shipping_address,
    #     weight_kg,
    #     order_is_cod,
    #     total_amount,
    # )
    # return _book_and_update(order, shipment, payment, user, courier_payload, log)
    return JsonResponse({"msg": "Order Created"})


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS ORDER CANCELLED
# ─────────────────────────────────────────────────────────────────────────────


def process_order_cancelled(
    user_id: int,
    shopify_order_id: str,
    payload: dict,
    log: WebhookLog | None = None,
    store: ShopifyStore | None = None,
) -> dict:
    """
    Cancel an order and its shipment when Shopify fires an orders/cancelled webhook.

    Steps:
        1.  Find order by shopify_order_id + channel + user
        2.  validate_order_cancellable
        3.  Cancel with courier if AWB exists → get refund_amount
        4.  Credit refund_amount back to wallet
        5.  Update order status to 'cancelled' via order.update_status()

    Returns:
        dict with keys: success, order_id, refund  (or error on failure)
    """
    logger.info(
        f"[process_order_cancelled] START | "
        f"user_id={user_id} shopify_order_id={shopify_order_id}"
    )

    from django.contrib.auth import get_user_model

    User = get_user_model()

    # ── FIND USER ─────────────────────────────────────────────────────────
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        _mark_log(log, "failed", f"User {user_id} not found.")
        return {"success": False, "error": "User not found."}

    # ── FIND ORDER ────────────────────────────────────────────────────────
    try:
        order = Order.objects.select_related(
            "payment", "shipment", "logistic_partner"
        ).get(
            order_number=shopify_order_id,
            channel="shopify",
            user=user,
        )
    except Order.DoesNotExist:
        # Could arrive before order/create — safely skip
        logger.info(
            f"[process_order_cancelled] Order {shopify_order_id} not found. "
            "Possibly never created. Skipping."
        )
        _mark_log(log, "processed", "Order not found in system — skipped.")
        return {"success": True, "note": "Order not found in system."}

    # ── VALIDATE CANCELLABLE ──────────────────────────────────────────────
    try:
        validate_order_cancellable(order)
    except ShopifyOrderValidationError as e:
        _mark_log(log, "failed", str(e))
        return {"success": False, "error": str(e)}

    awb = order.awb_number
    refund_amount = 0.0

    # ── CANCEL WITH COURIER ───────────────────────────────────────────────
    if awb:
        try:
            result = CourierService(user).cancel_shipment(awb)
            refund_amount = float(result.get("refund_amount") or 0.0)
        except CourierServiceError as e:
            logger.warning(
                f"[process_order_cancelled] Courier cancel failed for AWB {awb}: {e}. "
                "Proceeding with local cancellation only."
            )
            # Refund whatever we originally debited for shipping
            try:
                refund_amount = float(order.payment.shipping_charges or 0.0)
            except Exception:
                refund_amount = 0.0

    # ── REFUND WALLET + CANCEL ORDER ─────────────────────────────────────
    with transaction.atomic():
        if refund_amount > 0:
            txn = WalletTransaction.create_transaction(
                user=user,
                merchant_txn_id=_build_merchant_txn_id(order.id, "refund"),
                amount_rs=refund_amount,
                desc="shopify_cancellation_refund",
                transaction_type="credit",
            )
            txn.credit(awb_number=awb)
            logger.info(
                f"[process_order_cancelled] Refunded ₹{refund_amount} to {user.email}"
            )

        order.update_status("cancelled")

    Notification.objects.create(
        user=user,
        msg=(
            f"Shopify order #{shopify_order_id} has been cancelled."
            + (f" ₹{refund_amount} refunded to your wallet." if refund_amount else "")
        ),
        category="info",
    )

    _mark_log(log, "processed")
    logger.info(f"[process_order_cancelled] DONE | Order #{order.id} cancelled.")
    return {"success": True, "order_id": order.id, "refund": refund_amount}


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS ORDER UPDATED
# ─────────────────────────────────────────────────────────────────────────────


def process_order_updated(
    user_id: int,
    shopify_order_id: str,
    payload: dict,
    log: WebhookLog | None = None,
    store: ShopifyStore | None = None,
) -> dict:
    """
    Handle updates to an existing Shopify order (address change, note, total).

    Only mutates DB records if order is still in ready_to_ship or processing.
    Always refreshes order.json with the latest raw payload.

    Steps:
        1.  Find order by shopify_order_id + channel + user
        2.  If validate_order_updatable → update shipping address
        3.  Update notes and total_amount if changed
        4.  Always refresh order.json

    Returns:
        dict with keys: success, order_id, updated_fields  (or error on failure)
    """
    logger.info(
        f"[process_order_updated] START | "
        f"user_id={user_id} shopify_order_id={shopify_order_id}"
    )

    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        _mark_log(log, "failed", "User not found.")
        return {"success": False, "error": "User not found."}

    try:
        order = Order.objects.select_related("shipping_address").get(
            order_number=shopify_order_id,
            channel="shopify",
            user=user,
        )
    except Order.DoesNotExist:
        # Could arrive before order/create webhook — safe to skip
        _mark_log(log, "processed", "Order not found — skipped.")
        return {"success": True, "note": "Order not in system yet."}

    updated_fields = []

    with transaction.atomic():

        # ── UPDATE SHIPPING ADDRESS if still mutable ───────────────────────
        if validate_order_updatable(order):
            new_addr = payload.get("shipping_address") or {}
            if new_addr and order.shipping_address:
                updated_address = update_address_from_shopify(
                    order.shipping_address, new_addr
                )
                updated_address.save()
                logger.info(
                    f"[process_order_updated] Address updated for Order #{order.id}"
                )

        # ── UPDATE NOTES ───────────────────────────────────────────────────
        new_note = payload.get("note") or ""
        if new_note != order.notes:
            order.notes = new_note
            updated_fields.append("notes")

        # ── UPDATE TOTAL ───────────────────────────────────────────────────
        new_total = float(payload.get("total_price") or 0.0)
        if new_total and new_total != order.total_amount:
            order.total_amount = new_total
            order.invoice_amount = new_total
            updated_fields.extend(["total_amount", "invoice_amount"])

        # ── REFRESH RAW PAYLOAD ────────────────────────────────────────────
        order.json = payload
        updated_fields.append("json")

        if updated_fields:
            order.save(update_fields=updated_fields)

    _mark_log(log, "processed")
    logger.info(
        f"[process_order_updated] DONE | "
        f"Order #{order.id} | Updated fields: {updated_fields}"
    )
    return {
        "success": True,
        "order_id": order.id,
        "updated_fields": updated_fields,
    }
