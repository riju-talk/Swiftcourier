import logging
from typing import Dict, Any, Optional

import requests
from requests import Response
from django.conf import settings

from account import creds
from account.models import Courier
from order_manager.models import OrderItem


logger = logging.getLogger("my-logger")

ZIPPYY_BASE_URL = "https://sellingpartnerapi-in.zippyy.ai/v1/external"


# =========================
# Payload Builder
# =========================
def build_payload(order, hub) -> Dict[str, Any]:
    """
    Create payload for Zippyy API forward shipment.
    """
    payload = {
        "orderNumber": str(order.get_order_id()),
        "orderCreatedAt": str(
            int(order.created_at.timestamp() * 1000)
        ),  # convert to epoch ms
        "channelId": "External",
        "sender": {
            "firstName": hub.contact_person.split(" ")[0]
            if hub.contact_person
            else "N/A",
            "lastName": " ".join(hub.contact_person.split(" ")[1:])
            if hub.contact_person
            else "N/A",
            "email": hub.email if hasattr(hub, "email") else "N/A",
            "phoneNumber": hub.phone,
            "companyName": hub.name,
        },
        "origin": {
            "addressLine1": hub.address_line1,
            "addressLine2": hub.address_line2 or "N/A",
            "city": hub.city,
            "state": hub.state,
            "country": "India",
            "countryCode": "IN",
            "pinCode": hub.pin_code,
            "type": "Residential",
        },
        "receiver": {
            "firstName": order.shipping_address.name.split(" ")[0],
            "lastName": " ".join(order.shipping_address.name.split(" ")[1:]),
            "email": order.shipping_address.email
            if hasattr(order.shipping_address, "email") and order.shipping_address.email != ""
            else "not_available@idiotship.tech",
            "phoneNumber": order.shipping_address.phone,
            "companyName": "",
        },
        "destination": {
            "addressLine1": order.shipping_address.line1,
            "addressLine2": order.shipping_address.line2 or "N/A",
            "city": order.shipping_address.city,
            "state": order.shipping_address.state,
            "country": "India",
            "countryCode": "IN",
            "pinCode": order.shipping_address.pin_code,
            "type": "Residential",
        },
        "returnAddress": {
            "addressLine1": hub.address_line1,
            "addressLine2": hub.address_line2 or "N/A",
            "city": hub.city,
            "state": hub.state,
            "country": "India",
            "countryCode": "IN",
            "pinCode": hub.pin_code,
            "type": "Residential",
        },
        "type": "Zippyy",
        "sellerNote": "",
        "parcelAttributes": {
            "dimension": {
                "length": float(order.shipment.package_length_cm),
                "width": float(order.shipment.package_width_cm),
                "height": float(order.shipment.package_height_cm),
                "unit": "cm",
            },
            "weight": {"weight": float(order.shipment.package_weight_kg), "unit": "kg"},
        },
        "tags": "",
        "productRequestsList": [
            {
                "productName": item.product.name,
                "price": str(int(item.unit_price)),
                "quantity": item.quantity,
                "category": None,
                "currencyCode": "INR",
                "sku": item.sku_code,
                "taxRate": "0",
                "discount": "0",
                "description": None,
                "hs_code": None,
            }
            for item in OrderItem.objects.filter(order=order)
        ],
        "shippingProperties": {
            "orderType": "COD" if order.payment.method == "cod" else "PREPAID",
            "subTotal": float(order.total_amount),
            "shippingCharges": float(order.payment.shipping_charges),
            "otherCharges": float(order.payment.cod_charges),
            "discount": float(order.payment.discount),
        },
        "carrier": "Delhivery",
        "service": "Surface",
    }

    return payload


# =========================
# Base Request
# =========================
def zippyy_request(
    request_method: str,
    action_url: str,
    payload: Optional[dict] = None,
    headers: Optional[dict] = None,
    retry_count: int = 0,
    max_retries: int = 3,
) -> Response:
    url = f"{ZIPPYY_BASE_URL}{action_url}"
    headers = headers or {"Content-Type": "application/json"}

    # Auth header
    if creds.ZIPPYY_API_KEY:
        headers["Authorization"] = f"Bearer {creds.ZIPPYY_API_KEY}"

    res = requests.request(
        method=request_method.upper(),
        url=url,
        headers=headers,
        json=payload if payload else None,
    )

    # need to regenrate token or not to punch orders
    require_token_regeneration = False

    try:
        res_json = res.json()
        logger.info(f"Zippyy Response ({action_url}): {res_json}\nPayload: {payload}")
    except Exception:
        if res.text:
            logger.error(
                f"Non-JSON response from Zippyy: {res.text}\tLength of response: {len(res.text)}"
            )
            return res
        else:
            require_token_regeneration = True

    # Handle invalid token retry
    if (
        require_token_regeneration or res.status_code == 401
    ) and retry_count < max_retries:
        print("=============Generating token ")
        generate_token(settings.ZIPPYY_EMAIL, settings.ZIPPYY_PASSWORD)
        return zippyy_request(
            request_method,
            action_url,
            payload,
            headers,
            retry_count + 1,
            max_retries,
        )

    return res


# =========================
# Authentication
# =========================
def generate_token(email: str, password: str) -> Response:
    url = f"{ZIPPYY_BASE_URL}/auth/login"
    headers = {"x-api-version": "1", "Content-Type": "application/json"}
    payload = {"emailAddress": email, "password": password}
    res = requests.post(
        url=url,
        headers=headers,
        json=payload,
    )
    try:
        res_json = res.json()
        if res.status_code == 200 and "accessToken" in res_json:
            creds.ZIPPYY_API_KEY = res_json["accessToken"]
        else:
            logger.error(f"Failed to generate Zippyy token: {res_json}")
    except Exception as e:
        logger.error(
            f"Exception while generating Zippyy token: {e}\tResponse: {res.text}\tLength of response: {len(res.text)}"
        )
    return res


# =========================
# Shipment APIs
# =========================
def order_booking(shipment_data: Dict[str, Any]) -> Response:
    return zippyy_request("POST", "/shipments/forward-shipment", payload=shipment_data)


def track_shipment(awb_number: str) -> Response:
    return zippyy_request("GET", f"/shipments/{awb_number}")


def generate_label(awb_number: str) -> Response:
    return zippyy_request("GET", f"/shipments/{awb_number}/label-url")


def generate_invoice(awb_number: str) -> Response:
    return zippyy_request("GET", f"/shipments/{awb_number}/invoice")


def cancel_shipment(awb_number: str) -> Response:
    return zippyy_request("PUT", f"/shipments/{awb_number}/cancel")


# =========================
# Couriers & Serviceability
# =========================
def get_courier_list() -> Response:
    return zippyy_request("GET", "/couriers")


# =========================
# Ship Order Helper
# =========================
def ship_order(order, hub):
    """
    Ship an order via Zippyy API.
    """
    try:
        payload = build_payload(order, hub)
        response = order_booking(payload)
        res_json = response.json()

        if response.status_code in (200, 202) and res_json.get("success", True):
            data = res_json.get("data", {})

            order.json |= res_json
            order.awb_number = data.get("awb_number") or data.get("awb")
            order.update_status("pending_pickup")
            order.hub = hub
            order.logistic_partner = Courier.objects.get(abbreviation="zy")
            order.save()

            return True, res_json

        else:
            msg = res_json.get("error", res_json.get("message", "Unknown error"))
            logger.error(f"Zippyy Order Failed: {msg} | response={res_json}")
            return False, {"error": msg, "response": res_json}

    except Exception as e:
        logger.exception("Zippyy Ship Order Exception")
        return False, {"error": str(e)}
