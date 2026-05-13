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
from . import common


logger = logging.getLogger("my-logger")
base_url = "https://apiv2.shiprocket.in/v1/external"


# ==========================================================
# AUTH
# ==========================================================


def shiprocket_get_access_token() -> str:
    token = creds.SHIPROCKET_BD_AIR_500GM_API_KEY
    if token:
        return token

    url = f"{base_url}/auth/login"
    payload = {
        "email": settings.SHIPROCKET_BD_AIR_500GM_EMAIL,
        "password": settings.SHIPROCKET_BD_AIR_500GM_PASSWORD,
    }
    headers = {"Content-Type": "application/json"}

    res = requests.post(url, json=payload, headers=headers)
    res.raise_for_status()
    data = res.json()

    token = data.get("token")
    if not token:
        raise Exception("Failed to obtain Shiprocket token")

    creds.SHIPROCKET_BD_AIR_500GM_API_KEY = token
    return token


# ==========================================================
# BASE REQUEST
# ==========================================================


def shiprocket_request(
    request_method: str,
    payload: Optional[str],
    action_url: str,
    headers: Optional[dict] = None,
    base_url: str = "https://apiv2.shiprocket.in",
    api_url: str = "/v1/external",
    retry_count: int = 0,
    max_retries: int = 1,
) -> Response:
    url = f"{base_url}{api_url}{action_url}"
    headers = headers or {}
    headers.setdefault("Content-Type", "application/json")
    headers["Authorization"] = f"Bearer {shiprocket_get_access_token()}"

    logger.debug(f"Shiprocket Request Payload: {payload}")
    res = requests.request(
        method=request_method.upper(),
        url=url,
        headers=headers,
        data=payload if request_method.upper() != "GET" else None,
    )

    if res.status_code == 401 and retry_count < max_retries:
        return shiprocket_request(
            request_method,
            payload,
            action_url,
            headers,
            base_url,
            api_url,
            retry_count + 1,
            max_retries,
        )

    logger.info(f"Shiprocket Response: {res.text}")
    return res


# ==========================================================
# PICKUP LOCATION (WAREHOUSE)
# ==========================================================


def list_warehouse() -> Response:
    return common.list_warehouse(shiprocket_request)


def create_warehouse(hub: Hub) -> Response:
    return common.create_warehouse(hub, shiprocket_request)


def remove_warehouse(warehouse_id: int) -> Response:
    return common.remove_warehouse(warehouse_id, shiprocket_request)


# ==========================================================
# SHIPMENT
# ==========================================================


def order_booking(shipment_data: Dict[str, Any]) -> Response:
    return common.order_booking(
        shipment_data,
        shiprocket_request,
    )


def assign_awb(shipment_id: int) -> Response:
    return common.assign_awb(
        shipment_id,
        shiprocket_request,
    )


def track_shipment(awb_number: str) -> Response:
    return common.track_shipment(
        awb_number,
        shiprocket_request,
    )


def cancel_shipment(awb_number: str) -> Response:
    return common.cancel_shipment(
        awb_number,
        shiprocket_request,
    )


def get_courier_list(token: str = "") -> Response:
    return common.get_courier_list(
        shiprocket_request,
        token,
    )


# ==========================================================
# NDR
# ==========================================================


def get_ndr_list(ndr_type="initiated", from_date=None, to_date=None) -> Response:
    return common.get_ndr_list(
        shiprocket_request,
        ndr_type,
        from_date,
        to_date,
    )


def create_ndr_actions(awb_no: str) -> Response:
    return common.create_ndr_actions(
        awb_no,
        shiprocket_request,
    )


# ==========================================================
# HIGH LEVEL ORCHESTRATION
# ==========================================================


def ship_order(order: Order, hub: Hub):
    return common.ship_order(
        order,
        hub,
        "sr_bd_air_500",
        shiprocket_request,
        courier_id=22,
    )
