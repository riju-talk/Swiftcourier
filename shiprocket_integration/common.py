from collections.abc import Callable
import json
import logging
from typing import List, Dict, Any, Optional

import requests
from requests import Response
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from account import creds
from account.models import Courier
from order_manager.models import Hub, Order, OrderItem


logger = logging.getLogger("my-logger")
base_url = "https://apiv2.shiprocket.in/v1/external"


# ==========================================================
# PAYLOAD BUILDER
# ==========================================================


def build_payload(
    order: Order, hub: Hub, sr_request: Callable, mode="surface"
) -> Optional[Dict[str, Any]]:
    pickup_addr_exists = False
    pickup_res = list_warehouse(sr_request).json()

    for p in pickup_res.get("data", {}).get("shipping_address", []):
        if p.get("pickup_location") == hub.name:
            pickup_addr_exists = True
            break

    if not pickup_addr_exists:
        pickup_addr_res = create_warehouse(hub, sr_request).json()
        if pickup_addr_res.get("success"):
            pickup_addr_exists = True
        else:
            return False, {"error": pickup_addr_res.get("message")}

    items = []
    for item in OrderItem.objects.filter(order=order):
        items.append(
            {
                "name": item.product.name,
                "sku": item.sku_code,
                "units": item.quantity,
                "selling_price": int(item.unit_price),
                "discount": 0,
                "tax": 0,
                "hsn": "",
            }
        )

    payload = {
        "order_id": str(order.get_order_id()),
        "order_date": timezone.now().strftime("%Y-%m-%d %H:%M"),
        "pickup_location": hub.name,
        "billing_customer_name": order.billing_address.name,
        "billing_last_name": "N/A",
        "billing_address": order.billing_address.line1,
        "billing_address_2": order.billing_address.line2 or "",
        "billing_city": order.billing_address.city,
        "billing_pincode": order.billing_address.pin_code,
        "billing_state": order.billing_address.state,
        "billing_country": order.billing_address.country,
        "billing_email": order.billing_address.email,
        "billing_phone": order.billing_address.phone,
        "shipping_is_billing": False,
        "shipping_customer_name": order.shipping_address.name,
        "shipping_address": order.shipping_address.line1,
        "shipping_address_2": order.shipping_address.line2 or "",
        "shipping_city": order.shipping_address.city,
        "shipping_pincode": order.shipping_address.pin_code,
        "shipping_state": order.shipping_address.state,
        "shipping_country": order.shipping_address.country,
        "shipping_email": order.shipping_address.email,
        "shipping_phone": order.shipping_address.phone,
        "order_items": items,
        "payment_method": "COD" if order.payment.method == "cod" else "Prepaid",
        "sub_total": int(order.total_amount),
        "length": float(order.shipment.package_length_cm),
        "breadth": float(order.shipment.package_width_cm),
        "height": float(order.shipment.package_height_cm),
        "weight": float(order.shipment.package_weight_kg),
    }
    return payload, None


# ==========================================================
# PICKUP LOCATION (WAREHOUSE)
# ==========================================================


def list_warehouse(
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> Response:
    return sr_request("GET", None, "/settings/company/pickup")


def create_warehouse(
    hub: Hub,
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> Response:
    payload = {
        "pickup_location": hub.name,
        "name": hub.contact_person,
        "email": hub.email or "support@example.com",
        "phone": hub.phone,
        "address": hub.address_line1,
        "address_2": hub.address_line2 or "",
        "city": hub.city,
        "state": hub.state,
        "country": "India",
        "pin_code": hub.pin_code,
    }
    return sr_request(
        "POST",
        json.dumps(payload),
        "/settings/company/addpickup",
    )


def remove_warehouse(
    warehouse_id: int,
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> Response:
    return sr_request(
        "POST",
        json.dumps({"pickup_id": warehouse_id}),
        "/settings/company/deletepickup",
    )


# ==========================================================
# SHIPMENT
# ==========================================================


def order_booking(
    shipment_data: Dict[str, Any],
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> Response:
    return sr_request(
        "POST",
        json.dumps(shipment_data),
        "/orders/create/adhoc",
    )


def assign_awb(
    shipment_id: int,
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
    courier_id: Optional[int] = None,
) -> Response:
    payload = {"shipment_id": shipment_id}

    if courier_id is not None:
        payload["courier_id"] = courier_id

    return sr_request(
        "POST",
        json.dumps(payload),
        "/courier/assign/awb",
    )


def track_shipment(
    awb_number: str,
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> Response:
    return sr_request(
        "GET",
        None,
        f"/courier/track/awb/{awb_number}",
    )


def cancel_shipment(
    awb_number: str,
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> Response:
    return sr_request(
        "POST",
        json.dumps({"awbs": [awb_number]}),
        "/orders/cancel/shipment/awbs",
    )


def get_courier_list(
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
    token: str = "",
) -> Response:
    return sr_request("GET", None, "/courier/courierListWithCounts")


# ==========================================================
# NDR
# ==========================================================


def get_ndr_list(
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
    ndr_type="initiated",
    from_date=None,
    to_date=None,
) -> Response:
    return sr_request("GET", None, "/ndr/all")


def create_ndr_actions(
    awb_no: str,
    sr_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> Response:
    return sr_request(
        "POST",
        json.dumps(
            {"action": "return", "comments": "The Buyer does not want the product"}
        ),
        f"/ndr/{awb_no}/action",
    )


# ==========================================================
# HIGH LEVEL ORCHESTRATION
# ==========================================================


def ship_order(
    order: Order,
    hub: Hub,
    courier_abbreviation: str,
    sr_request: Callable,
    courier_id: Optional[int] = None,
):
    try:
        try:
            shipment_id = (
                order.json.get("awb", {})
                .get("response", {})
                .get("data", {})
                .get("shipment_id")
            )
        except Exception:
            shipment_id = None

        logger.debug(f"Existing Shipment ID: {shipment_id}")
        if not shipment_id:
            payload, error = build_payload(order, hub, sr_request)
            if not payload:
                return False, {
                    "error": f"Failed to build payload. Error: {error.get('error')}"
                }

            logger.debug(f"Shiprocket Order Payload: {payload}")

            res = order_booking(payload, sr_request).json()
            if "shipment_id" not in res:
                return False, {"error": res.get("message", "Unknown Error").replace("Shiprocket", "SwiftCourier").replace("SHIPROCKET", "SwiftCourier").replace("shiprocket", "SwiftCourier")}

            logger.debug(f"Shiprocket Order Booking Response: {res}")

            shipment_id = res["shipment_id"]

        awb_res = assign_awb(shipment_id, sr_request, courier_id=courier_id).json()
        logger.debug(
            f"Shiprocket AWB Assignment Response for order id {order.id}: {awb_res}"
        )

        if awb_res.get("awb_assign_status") == 0:
            abcd = awb_res.get("response", {}).get("data", {})
            if isinstance(abcd, str):
                return False, {"error": abcd}
            logger.debug(
                f'AWB Assignment Failed: {awb_res.get("response", {}).get("data", {}).get("awb_assign_error")}'
            )
            return False, {
                "error": awb_res.get("response", {})
                .get("data", {})
                .get("awb_assign_error")
            }

        awb = awb_res.get("response", {}).get("data", {}).get("awb_code")
        if not awb:
            return False, {"error": awb_res.get("message")}

        order.json |= {"awb": awb_res}
        try:
            order.json |= {"order": res}
        except Exception:
            pass

        order.awb_number = awb
        order.update_status("pending_pickup")
        order.hub = hub
        order.logistic_partner = Courier.objects.get(abbreviation=courier_abbreviation)
        order.save()

        return True, awb_res

    except Exception as e:
        logger.exception("Shiprocket Ship Order Exception")
        return False, {"error": str(e)}
