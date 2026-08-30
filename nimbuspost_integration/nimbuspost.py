"""
NimbusPost partner-API client.

NimbusPost runs the same shipping platform as Xpressbees, so this module is a
close sibling of ``xpressbees_integration/xpressbees.py`` - the request helper,
the login/retry dance and the shipment payload are all the same shape. The
differences that matter:

  * base URL is ``https://api.nimbuspost.com/v1`` (see constants.BASE_URL)
  * login lives at ``settings.NIMBUS_POST_URL`` with ``settings.NIMBUS_API_EMAIL``
    / ``settings.NIMBUS_API_PASS``
  * every outbound call has an explicit timeout and never lets a transport
    error escape into the caller

Public surface consumed by the rest of the app (matches the other couriers):

  * ``ship_order(order, hub) -> (bool, dict)``      - order_manager ship task
  * ``cancel_shipment(awb_number) -> requests.Response`` - cancel_order view
  * ``track_shipment(awb_number) -> requests.Response``
  * ``generate_label(orders) -> (err, url_list)``   - label flow (best effort)
  * ``generate_manifest`` / ``check_serviceability`` / ``get_courier_list``
"""

import json
import logging
from typing import Any, Optional

import requests
from django.conf import settings

from account import creds
from account.models import Courier
from order_manager.models import OrderItem

from .constants import (
    AUTH_FAILURE_HINTS,
    BASE_URL,
    MAX_AUTH_RETRIES,
    REQUEST_TIMEOUT,
    STATUS_MAPPING,
)

logger = logging.getLogger("my-logger")

COURIER_ABBREVIATION = "nimbuspost"


# --------------------------------------------------------------------------- #
# low-level HTTP
# --------------------------------------------------------------------------- #
def _safe_json(response: requests.Response) -> dict:
    """Return the parsed JSON body, or ``{}`` if the response isn't JSON."""
    try:
        body = response.json()
    except ValueError:
        logger.error(
            "NimbusPost:: non-JSON response (%s) from %s: %.500r",
            response.status_code,
            response.url,
            response.text,
        )
        return {}
    return body if isinstance(body, dict) else {"data": body}


def _looks_like_auth_failure(response: requests.Response, body: dict) -> bool:
    if response.status_code in (401, 403):
        return True
    if body.get("status") in (True, 1, "1"):
        return False
    message = str(body.get("message", "")).lower()
    return any(hint in message for hint in AUTH_FAILURE_HINTS)


def generate_token() -> bool:
    """
    Log in to NimbusPost and cache the bearer token on ``creds``.

    Returns True on success. Never raises.
    """
    email = settings.NIMBUS_API_EMAIL
    password = settings.NIMBUS_API_PASS
    if not email or not password:
        logger.error("NimbusPost:: NIMBUS_API_EMAIL / NIMBUS_API_PASS not configured")
        return False

    try:
        response = requests.post(
            settings.NIMBUS_POST_URL,
            data=json.dumps({"email": email, "password": password}),
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        logger.exception("NimbusPost:: login request failed")
        return False

    body = _safe_json(response)
    token = body.get("data")
    if not body.get("status") or not isinstance(token, str) or not token:
        logger.error("NimbusPost:: login rejected: %s", body or response.text[:500])
        return False

    creds.NIMBUSPOST_API_KEY = token
    logger.info("NimbusPost:: obtained a fresh bearer token")
    return True


def nimbuspost_request(
    method: str,
    action_url: str,
    payload: Optional[dict] = None,
    *,
    authed: bool = True,
    _auth_retry: int = 0,
) -> requests.Response:
    """
    Fire a single request at the NimbusPost API.

    ``action_url`` is the path after the version segment, e.g. ``/shipments``.
    On an auth failure the token is refreshed and the call retried up to
    ``MAX_AUTH_RETRIES`` times. Transport errors are re-raised as
    ``requests.RequestException`` so callers can decide what to do; every
    public helper below turns that into a structured error instead.
    """
    if authed and not creds.NIMBUSPOST_API_KEY:
        generate_token()

    headers = {"Content-Type": "application/json"}
    if authed and creds.NIMBUSPOST_API_KEY:
        headers["Authorization"] = f"Bearer {creds.NIMBUSPOST_API_KEY}"

    url = f"{BASE_URL}{action_url}"
    method = method.upper()

    response = requests.request(
        method,
        url,
        headers=headers,
        data=json.dumps(payload) if payload is not None and method != "GET" else None,
        params=payload if method == "GET" else None,
        timeout=REQUEST_TIMEOUT,
    )

    body = _safe_json(response)
    logger.info("NimbusPost:: %s %s -> %s", method, action_url, response.status_code)

    if (
        authed
        and _auth_retry < MAX_AUTH_RETRIES
        and _looks_like_auth_failure(response, body)
    ):
        logger.warning("NimbusPost:: token rejected, re-logging in (attempt %s)", _auth_retry + 1)
        if generate_token():
            return nimbuspost_request(
                method, action_url, payload, authed=authed, _auth_retry=_auth_retry + 1
            )

    return response


# --------------------------------------------------------------------------- #
# thin endpoint wrappers
# --------------------------------------------------------------------------- #
def order_booking(shipment_data: dict) -> requests.Response:
    return nimbuspost_request("POST", "/shipments", shipment_data)


def track_shipment(awb_number: str) -> requests.Response:
    return nimbuspost_request("GET", f"/shipments/track/{awb_number}")


def bulk_track_shipment(awb_numbers: list[str]) -> requests.Response:
    return nimbuspost_request("POST", "/shipments/track/bulk", {"awb": awb_numbers})


def cancel_shipment(awb_number: str) -> requests.Response:
    return nimbuspost_request("POST", "/shipments/cancel", {"awb": awb_number})


def generate_manifest(awb_list: list[str]) -> requests.Response:
    return nimbuspost_request("POST", "/shipments/manifest", {"awbs": awb_list})


def get_courier_list() -> requests.Response:
    return nimbuspost_request("GET", "/courier")


def check_serviceability(
    origin: str,
    destination: str,
    payment_type: str,
    order_amount: Any,
    weight: Optional[Any] = None,
    length: Optional[Any] = None,
    breadth: Optional[Any] = None,
    height: Optional[Any] = None,
) -> requests.Response:
    payload = {
        "origin": origin,
        "destination": destination,
        "payment_type": payment_type,
        "order_amount": order_amount,
    }
    for key, value in (
        ("weight", weight),
        ("length", length),
        ("breadth", breadth),
        ("height", height),
    ):
        if value is not None:
            payload[key] = value
    return nimbuspost_request("POST", "/courier/serviceability", payload)


# --------------------------------------------------------------------------- #
# payload building
# --------------------------------------------------------------------------- #
def build_payload(order, hub) -> dict:
    """Assemble the NimbusPost create-shipment body for ``order`` from ``hub``."""
    payment = order.payment
    shipment = order.shipment
    address = order.shipping_address

    is_cod = payment.method == "cod"

    return {
        "order_number": str(order.get_order_id_for_aggregator()),
        "unique_order_number": "no",
        "shipping_charges": payment.shipping_charges or 0,
        "discount": payment.discount or 0,
        "cod_charges": payment.cod_charges or 0,
        "payment_type": "cod" if is_cod else "prepaid",
        "order_amount": order.total_amount,
        "package_weight": int((shipment.package_weight_kg or 0) * 1000),
        "package_length": int(shipment.package_length_cm or 0),
        "package_breadth": int(shipment.package_width_cm or 0),
        "package_height": int(shipment.package_height_cm or 0),
        "request_auto_pickup": "yes",
        "consignee": {
            "name": address.name,
            "address": address.line1,
            "address_2": address.line2 or "",
            "city": address.city,
            "state": address.state,
            "pincode": address.pin_code,
            "phone": address.phone,
        },
        "pickup": {
            "warehouse_name": hub.name,
            "name": hub.contact_person or hub.name,
            "address": hub.address_line1,
            "address_2": hub.address_line2 or "",
            "city": hub.city,
            "state": hub.state,
            "pincode": hub.pin_code,
            "phone": hub.phone,
        },
        "order_items": [
            {
                "name": item.product.name,
                "qty": str(item.quantity),
                "price": str(int(item.unit_price)),
                "sku": item.sku_code,
            }
            for item in OrderItem.objects.filter(order=order).select_related("product")
        ],
        "courier_id": "",
        "collectable_amount": str(order.total_amount) if is_cod else "0",
    }


# --------------------------------------------------------------------------- #
# handler surface used by order_manager
# --------------------------------------------------------------------------- #
def _courier() -> Optional[Courier]:
    return Courier.objects.filter(abbreviation=COURIER_ABBREVIATION).first()


def ship_order(order, hub) -> tuple[bool, dict]:
    """
    Push a single order to NimbusPost.

    Returns ``(True, response_json)`` on success or ``(False, {"error": ...})``
    on any failure. Never raises - the ship task treats a raised exception the
    same as a hard failure but the structured error is far more useful.
    """
    try:
        payload = build_payload(order, hub)
    except Exception as exc:
        logger.exception("NimbusPost:: could not build payload for order #%s", order.id)
        return False, {"error": f"payload build failed: {exc}"}

    try:
        response = order_booking(payload)
    except requests.RequestException as exc:
        logger.exception("NimbusPost:: ship request failed for order #%s", order.id)
        return False, {"error": f"network error: {exc}"}

    body = _safe_json(response)

    if not body.get("status"):
        message = body.get("message") or response.text[:300] or "unknown error"
        logger.error("NimbusPost:: ship failed for order #%s: %s", order.id, message)
        return False, {"error": message, "response": body}

    data = body.get("data") or {}
    awb = data.get("awb_number")
    if not awb:
        logger.error("NimbusPost:: ship response for order #%s had no AWB: %s", order.id, body)
        return False, {"error": "NimbusPost returned no AWB", "response": body}

    order.json = {**(order.json or {}), "nimbuspost": body}
    order.awb_number = awb
    order.route_code = data.get("routing_code") or order.route_code
    order.hub = hub
    order.logistic_partner = _courier()
    order.save()
    order.update_status("pending_pickup")

    logger.info("NimbusPost:: order #%s booked, AWB %s", order.id, awb)
    return True, body


def cancel_order(order) -> tuple[bool, dict]:
    """Cancel ``order`` with NimbusPost by its AWB. Never raises."""
    if not order.awb_number:
        return False, {"error": "order has no AWB to cancel"}
    try:
        response = cancel_shipment(order.awb_number)
    except requests.RequestException as exc:
        logger.exception("NimbusPost:: cancel request failed for order #%s", order.id)
        return False, {"error": f"network error: {exc}"}

    body = _safe_json(response)
    if response.status_code != 200 or not body.get("status"):
        message = body.get("message") or response.text[:300] or "unknown error"
        return False, {"error": message, "response": body}
    return True, body


def generate_label(orders) -> tuple[Optional[str], list[str]]:
    """
    Best-effort label URL collection.

    NimbusPost hands back a ``label`` URL in the create-shipment response, which
    ``ship_order`` stores under ``order.json["nimbuspost"]["data"]["label"]``.
    Pull those rather than making another API call. Returns ``(err, urls)``.
    """
    urls: list[str] = []
    missing: list[str] = []
    for order in orders:
        label = (
            (order.json or {})
            .get("nimbuspost", {})
            .get("data", {})
            .get("label")
        )
        if label:
            urls.append(label)
        else:
            missing.append(str(order.id))
    if missing:
        return f"no stored NimbusPost label for order(s): {', '.join(missing)}", urls
    return None, urls


# --------------------------------------------------------------------------- #
# tracking helper (shared shape with the webhook status handling)
# --------------------------------------------------------------------------- #
def map_status(raw_status: str) -> Optional[str]:
    """Translate a raw NimbusPost status string to an internal order status."""
    if raw_status is None:
        return None
    return STATUS_MAPPING.get(str(raw_status).strip().lower())
