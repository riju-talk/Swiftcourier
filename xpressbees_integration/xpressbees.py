import json
import logging
from typing import List, Dict, Any, Optional

from django.conf import settings
from account import creds
import requests
from requests import Response

from account.models import Courier
from order_manager.models import OrderItem


logger = logging.getLogger("my-logger")


# xpressbees_integration/xpressbees.py
def build_payload(order, hub):
    """
    Create payload for Xpressbees API.
    """
    payload = {
        "order_number": str(order.get_order_id()),
        "unique_order_number": "no",
        "shipping_charges": order.payment.shipping_charges,
        "discount": order.payment.discount,
        "cod_charges": order.payment.cod_charges,
        "payment_type": order.payment.method,
        "order_amount": order.total_amount,
        "package_weight": int(order.shipment.package_weight_kg * 1000),
        "package_length": int(order.shipment.package_length_cm),
        "package_breadth": int(order.shipment.package_width_cm),
        "package_height": int(order.shipment.package_height_cm),
        "request_auto_pickup": "yes",
        "consignee": {
            "name": order.shipping_address.name,
            "address": order.shipping_address.line1,
            "address_2": order.shipping_address.line2 or "",
            "city": order.shipping_address.city,
            "state": order.shipping_address.state,
            "pincode": order.shipping_address.pin_code,
            "phone": order.shipping_address.phone,
        },
        "pickup": {
            "warehouse_name": hub.name,
            "name": hub.contact_person,  # adjust field name as needed
            "address": hub.address_line1,  # adjust field name as needed
            "address_2": hub.address_line2 or "",
            "city": hub.city,
            "state": hub.state,
            "pincode": hub.pin_code,
            "phone": hub.phone,  # adjust field name as needed
        },
        # only included when RTO differs
        # **(
        #     {
        #         "is_rto_different": "yes",
        #         "rto": {
        #             "warehouse_name": data.get("rto_warehouse_name", ""),
        #             "name": data.get("rto_name", ""),
        #             "address": data.get("rto_address", ""),
        #             "address_2": data.get("rto_address_2", ""),
        #             "city": data.get("rto_city", ""),
        #             "state": data.get("rto_state", ""),
        #             "pincode": data.get("rto_pincode", ""),
        #             "phone": data.get("rto_phone", ""),
        #         },
        #     }
        #     if data.get("is_rto_different") == "yes"
        #     else {}
        # ),
        "order_items": [
            {
                "name": item.product.name,
                "qty": str(item.quantity),
                "price": str(int(item.unit_price)),
                "sku": item.sku_code,
            }
            for item in OrderItem.objects.filter(
                order=order
            )  # TODO: cross-check item fields
        ],
        "courier_id": "",
        "collectable_amount": str(order.total_amount)
        if order.payment.method == "cod"
        else "0",
    }
    return payload


# Base request function
def xpressbees_request(
    request_method: str,
    payload: Optional[str],
    action_url: str,
    headers: Optional[dict] = None,
    base_url: str = "https://shipment.xpressbees.com",
    api_url: str = "/api",
    content_type: str = "application/json",
    is_api_key_required: bool = True,
    retry_count: int = 0,
    max_retries: int = 3,
) -> Response:
    url = f"{base_url}{api_url}{action_url}"
    headers = headers or {}
    headers.setdefault("Content-Type", content_type)

    if is_api_key_required:
        headers["Authorization"] = f"Bearer {creds.XPRESSBEES_API_KEY}"

    res = requests.request(
        method=request_method.upper(),
        url=url,
        headers=headers,
        data=payload if request_method.upper() != "GET" else None,
    )
    res_json = res.json()
    logger.info(f"Xpressbees Response: {res_json}")
    if (
        not res_json["status"]
        and res_json["message"] == "Missing or invalid Token in request"
        and retry_count < max_retries
    ):
        # Generate a new token and retry the request
        generate_token(settings.XPRESSBEES_USERNAME, settings.XPRESSBEES_PASSWORD)
        return xpressbees_request(
            request_method,
            payload,
            action_url,
            headers,
            base_url,
            api_url,
            content_type,
            is_api_key_required,
            retry_count + 1,
            max_retries,
        )

    return res


# Authentication
def generate_token(email: str, password: str) -> Response:
    res = xpressbees_request(
        "POST",
        json.dumps({"email": email, "password": password}),
        "/users/login",
        is_api_key_required=False,
    )
    res_json = res.json()
    if res_json["status"]:
        creds.XPRESSBEES_API_KEY = res_json["data"]

    return res


# Shipment creation
def order_booking(shipment_data: Dict[str, Any]) -> Response:
    return xpressbees_request(
        "POST",
        json.dumps(shipment_data),
        "/shipments2",
        headers={},
    )


# Shipment tracking
def track_shipment(awb_number: str) -> Response:
    return xpressbees_request(
        "GET",
        None,
        f"/shipments2/track/{awb_number}",
        headers={},
    )


# Generate manifest
def generate_manifest(awb_list: List[str]) -> Response:
    return xpressbees_request(
        "POST",
        json.dumps({"awbs": awb_list}),
        "/shipments2/manifest",
        headers={},
    )


# Cancel shipment
def cancel_shipment(awb_number: str) -> Response:
    return xpressbees_request(
        "POST",
        json.dumps({"awb": awb_number}),
        "/shipments2/cancel",
        headers={},
    )


# Get courier list
def get_courier_list(token: str) -> Response:
    return xpressbees_request("GET", None, "/courier", headers={})


# Serviceability check
def check_serviceability(
    token: str,
    origin: str,
    destination: str,
    payment_type: str,
    order_amount: str,
    weight: Optional[str] = None,
    length: Optional[str] = None,
    breadth: Optional[str] = None,
    height: Optional[str] = None,
) -> Response:
    payload = {
        "origin": origin,
        "destination": destination,
        "payment_type": payment_type,
        "order_amount": order_amount,
    }
    optional_fields = {
        "weight": weight,
        "length": length,
        "breadth": breadth,
        "height": height,
    }
    payload.update({k: v for k, v in optional_fields.items() if v is not None})

    return xpressbees_request(
        "POST",
        json.dumps(payload),
        "/courier/serviceability",
        headers={},
    )


# NDR List
def get_ndr_list(
    token: str,
    awb_numbers: Optional[List[str]] = None,
    per_page: Optional[int] = None,
    page: Optional[int] = None,
    max_records: Optional[int] = None,
) -> Response:
    query = []
    if awb_numbers:
        query.append(f"awb_number={','.join(awb_numbers)}")
    if per_page:
        query.append(f"per_page={per_page}")
    if page:
        query.append(f"page={page}")
    if max_records:
        query.append(f"max_records={max_records}")

    action = "/ndr"
    if query:
        action += "?" + "&".join(query)

    return xpressbees_request("GET", None, action, headers={})


# NDR actions
def create_ndr_actions(actions: List[Dict[str, Any]]) -> Response:
    return xpressbees_request(
        "POST",
        json.dumps(actions),
        "/ndr/create",
        headers={},
    )


def ship_order(order, hub):
    """
    Ship an order via Xpressbees API.

    :param order: Order instance
    :param hub: Hub instance
    :param payload: dict payload from build_payload()
    :return: (success: bool, response: dict)
    """
    try:
        payload = build_payload(order, hub)
        # Make API request
        response = order_booking(payload)
        res_json = response.json()

        # ✅ Success
        if res_json.get("status") is True:
            data = res_json.get("data", {})

            order.json |= res_json
            order.awb_number = data.get("awb_number")
            order.update_status("pending_pickup")
            order.hub = hub
            order.logistic_partner = Courier.objects.get(abbreviation="xb")
            order.save()

            return True, res_json

        # ❌ Failed
        else:
            message = res_json.get("message", "Unknown error")
            logger.error(f"Xpressbees Order Failed: {message}\nresponse: {res_json}")
            return False, {"error": message, "response": res_json}

    except Exception as e:
        logger.exception("Xpressbees Ship Order Exception")
        return False, {"error": str(e)}
