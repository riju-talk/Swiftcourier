import json
from typing import List, Dict, Any, Optional

from django.conf import settings
from account import creds
import requests
from requests import Response


# ---------- Base Request ----------
def lastmiles_request(
    request_method: str,
    payload: Optional[str],
    action_url: str,
    headers: Optional[dict] = None,
    base_url: str = "https://api.lastmiles.co/api/v1",
    content_type: str = "application/json",
    is_token_required: bool = True,
    retry_count: int = 0,
    max_retries: int = 3,
) -> Response:
    """
    Generic request wrapper for LastMiles API
    """
    url = f"{base_url}{action_url}"
    headers = headers or {}
    headers.setdefault("Content-Type", content_type)

    if is_token_required and creds.LASTMILES_API_KEY:
        headers["Authorization"] = f"Bearer {creds.LASTMILES_API_KEY}"

    res = requests.request(
        method=request_method.upper(),
        url=url,
        headers=headers,
        data=payload if request_method.upper() != "GET" else None,
    )

    try:
        res_json = res.json()
    except Exception:
        return res

    if (
        not res_json.get("status", True)
        and "invalid token" in res_json.get("message", "").lower()
        and retry_count < max_retries
    ):
        # refresh token and retry
        generate_token(settings.LASTMILES_EMAIL, settings.LASTMILES_PASSWORD)
        return lastmiles_request(
            request_method,
            payload,
            action_url,
            headers,
            base_url,
            content_type,
            is_token_required,
            retry_count + 1,
            max_retries,
        )

    return res


# ---------- Authentication ----------
def generate_token(email: str, password: str) -> Response:
    """
    Login and fetch new JWT token
    """
    payload = {
        "email": email,
        "password": password,
    }
    headers = {
        "Content-Type": "application/json",
    }

    res = lastmiles_request(
        "POST",
        json.dumps(payload),
        "/login",
        headers=headers,
        is_token_required=False,
    )
    res_json = res.json()
    if res_json.get("status"):
        creds.LASTMILES_API_KEY = res_json["data"]["access_token"]

    return res


# ---------- Pickup Location ----------
def add_pickup_location(location_data: Dict[str, Any]) -> Response:
    return lastmiles_request(
        "POST",
        json.dumps(location_data),
        "/pickuplocation/add",
    )


# ---------- Order Booking ----------
def order_booking(order_data: Dict[str, Any]) -> Response:
    return lastmiles_request(
        "POST",
        json.dumps(order_data),
        "/orders/create",
    )


# ---------- Track Shipment ----------
def track_shipment(awb_number: str) -> Response:
    return lastmiles_request(
        "GET",
        None,
        f"/shipment/external/tracking/awb/{awb_number}",
    )


# ---------- Cancel Shipment ----------
def cancel_shipment(awb_numbers: List[str]) -> Response:
    return lastmiles_request(
        "POST",
        json.dumps({"awb_numbers": awb_numbers}),
        "/shipment/cancel/awbs",
    )


# ---------- Generate Label ----------
def generate_label(order_ids: List[str]) -> Response:
    return lastmiles_request(
        "POST",
        json.dumps({"order_ids": order_ids}),
        "/shipment/generate-label/",
    )


# ---------- Health Check ----------
def system_health() -> Response:
    return lastmiles_request(
        "POST",
        None,
        "/status",
        is_token_required=False,
    )
