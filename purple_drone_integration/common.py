# purple_drone_integration/purple_drone.py
from collections.abc import Callable
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import requests
from django.conf import settings
from django.utils import timezone

from account import creds
from account.models import Courier
from order_manager.models import OrderItem

logger = logging.getLogger("my-logger")


# Helper: build payload for PurpleDrone 'allocate_waybill' API
def build_payload(order, hub, return_shipment: bool = False) -> Dict[str, Any]:
    """
    Build payload for PurpleDrone /order_allocation/api/allocate_waybill
    Based on the API spec in the uploaded PDF. Mandatory fields included.
    See the uploaded doc for full spec. :contentReference[oaicite:1]{index=1}
    """
    # Helper to format order date: dd-MMM-YYYY HH:MM:SS (example in docs)
    dt = (
        getattr(order, "created_at", None)
        or timezone.now()
    )
    if isinstance(dt, datetime):
        order_date = dt.strftime("%d-%b-%Y %H:%M:%S")
    else:
        # if it's a string already, assume it's ok; otherwise fallback to now
        try:
            order_date = str(dt)
        except Exception:
            order_date = timezone.now().strftime("%d-%b-%Y %H:%M:%S")

    # convert weight to grams; docs expect weight in grams (string/float)
    package_weight_grams = float(order.shipment.package_weight_kg * 1000)

    # convert dimensions to mm. Your shipment attributes appear to be in cm in xpressbees file.
    # multiply cm by 10 -> mm
    length_mm = float(getattr(order.shipment, "package_length_cm", 0) * 10)
    breadth_mm = float(getattr(order.shipment, "package_width_cm", 0) * 10)
    height_mm = float(getattr(order.shipment, "package_height_cm", 0) * 10)

    # items
    items = []
    for item in OrderItem.objects.filter(order=order):
        items.append(
            {
                "name": item.product.name,
                "description": getattr(item.product, "short_description", "")
                or item.product.name,
                "quantity": int(item.quantity),
                "skuCode": item.sku_code or "",
                "itemPrice": float(item.unit_price),
                "hsnCode": getattr(item.product, "hsn_code", "") or "",
                "imageURL": getattr(item.product, "image_url", "") or "",
            }
        )

    payment_mode = (
        "COD" if getattr(order.payment, "method", "").lower() == "cod" else "PREPAID"
    )

    payload = {
        "source": "api",
        "returnShipmentFlag": bool(return_shipment),
        "Shipment": {
            "code": getattr(
                creds,
                "PURPLEDRONE_CLIENT_CODE",
                getattr(settings, "PURPLEDRONE_CLIENT_CODE", ""),
            ),
            "orderCode": str(order.get_order_id()),
            "saleOrderCode": "",  # if you have split shipments you can set this
            "invoiceCode": getattr(order, "invoice_code", "") or "",
            "orderDate": order_date,
            "weight": str(package_weight_grams),
            "length": str(length_mm),
            "height": str(height_mm),
            "breadth": str(breadth_mm),
            "items": items,
        },
        "deliveryAddressDetails": {
            "name": order.shipping_address.name,
            "email": getattr(order.shipping_address, "email", "") or "",
            "phone": order.shipping_address.phone,
            "address1": order.shipping_address.line1,
            "address2": order.shipping_address.line2 or "",
            "pincode": str(order.shipping_address.pin_code),
            "city": order.shipping_address.city,
            "state": order.shipping_address.state,
            "country": getattr(order.shipping_address, "country", "India"),
            "gstin": getattr(order.shipping_address, "gstin", "") or "",
        },
        "pickupAddressDetails": {
            "name": hub.name,
            "email": getattr(hub, "email", "") or "",
            "phone": getattr(hub, "phone", "") or "",
            "address1": getattr(hub, "address_line1", "") or "",
            "address2": getattr(hub, "address_line2", "") or "",
            "pincode": str(hub.pin_code),
            "city": getattr(hub, "city", "") or "",
            "state": getattr(hub, "state", "") or "",
            "country": getattr(hub, "country", "India"),
            "gstin": getattr(hub, "gstin", "") or "",
        },
        "returnAddressDetails": {
            "name": getattr(hub, "name", ""),
            "email": getattr(hub, "email", "") or "",
            "phone": getattr(hub, "phone", "") or "",
            "address1": getattr(hub, "address_line1", "") or "",
            "address2": getattr(hub, "address_line2", "") or "",
            "pincode": str(hub.pin_code),
            "city": getattr(hub, "city", "") or "",
            "state": getattr(hub, "state", "") or "",
            "country": getattr(hub, "country", "India"),
            "gstin": getattr(hub, "gstin", "") or "",
        },
        "currencyCode": getattr(order, "currency", "INR"),
        "paymentMode": payment_mode,
        "totalAmount": str(float(order.total_amount)),
        "collectableAmount": str(float(order.total_amount))
        if payment_mode == "COD"
        else "0",
    }

    logger.info(f"Here is the full payload: {payload}")
    return payload


# Waybill generation (order booking)
def order_booking(
    shipment_data: Dict[str, Any],
    pd_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:
    """
    POST to /order_allocation/api/allocate_waybill
    See API doc for payload structure. :contentReference[oaicite:3]{index=3}
    """
    return pd_request(
        "POST",
        shipment_data,
        "/order_allocation/api/allocate_waybill",
        headers={},
    )


# Cancel order (POST /cancel)
def cancel_shipment(
    waybill: str,
    pd_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:
    return pd_request("POST", {"waybill": waybill}, "/cancel", headers={})


# Track / fetch order status
def track_shipment(
    awb_number: str,
    pd_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:
    """
    GET /api/orders?query_type=track&query_value=<awb>
    """
    action = f"/api/orders?query_type=track&query_value={awb_number}"
    return pd_request("GET", None, action, headers={})


# Ship order interface used by central task (same return shape as xpressbees.ship_order)
def ship_order(
    order,
    hub,
    courier_abbreviation: str,
    pd_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
    return_shipment: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Ship an order via PurpleDrone API.
    Returns (True, response_json) on success; (False, {"error": msg, "response": res_json}) on failure.
    """
    try:
        payload = build_payload(order, hub, return_shipment=return_shipment)
        response = order_booking(payload, pd_request)
        try:
            res_json = response.json()
        except Exception:
            logger.error(
                f"PurpleDrone non-json response for order {order.id}: {response.text}\nURL:{response.url}"
            )
            return False, {"error": "non-json response", "response_text": response.text}

        # Success case (docs: status == "SUCCESS")
        if str(res_json.get("status", "")).upper() == "SUCCESS":
            waybill = (
                res_json.get("waybill")
                or res_json.get("waybill_no")
                or res_json.get("data", {}).get("waybill")
            )
            # Save to order similar to xpressbees implementation
            order.json |= res_json
            if waybill:
                order.awb_number = waybill
            order.update_status("pending_pickup")
            order.hub = hub
            try:
                order.logistic_partner = Courier.objects.get(abbreviation=courier_abbreviation)
            except Courier.DoesNotExist:
                # fallback: do not crash if courier entry not present
                logger.warning(
                    "Courier with abbreviation 'pd' not found. Leaving logistic_partner unchanged."
                )
            order.save()
            return True, res_json

        # Failed
        else:
            message = (
                res_json.get("reason")
                or res_json.get("message")
                or res_json.get("detail")
                or res_json.get("error")
                or "Unknown error"
            )

            logger.error(f"PurpleDrone Order Failed: {message}\nresponse: {res_json}")
            return False, {"error": message, "response": res_json}

    except Exception as e:
        logger.exception("PurpleDrone Ship Order Exception")
        return False, {"error": str(e)}
