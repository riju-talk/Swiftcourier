"""RapidShyp serviceability adapter for the serviceability app.

Self-contained; reuses only ``rapidshyp_integration.common.rapidshyp_request``.
"""

import logging
from collections.abc import Callable
from typing import Optional

import requests

from rapidshyp_integration.common import rapidshyp_request

logger = logging.getLogger("my-logger")


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _extract_serviceability_items(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    items = payload.get("serviceable_courier_list")
    if isinstance(items, list):
        return items

    data = payload.get("data")
    if isinstance(data, dict):
        items = data.get("serviceable_courier_list")
        if isinstance(items, list):
            return items

    return []


def _serviceability_request(payload: dict) -> "requests.Response":
    response = rapidshyp_request("POST", payload, "/serviceabilty_check")
    if response.status_code == 404:
        response = rapidshyp_request("POST", payload, "/serviceability_check")
    return response


def check_serviceability(
    pickup_pincode: str,
    destination_pincode: str,
    couriers: Optional[list[str]] = None,
    rs_request: Callable = _serviceability_request,
    _aggregator_label: str = "RapidShyp",
) -> dict:
    payload = {
        "Pickup_pincode": str(pickup_pincode),
        "Delivery_pincode": str(destination_pincode),
        "cod": False,
        "total_order_value": 0,
        "weight": 0.5,
    }

    try:
        response = rs_request(payload)
    except Exception as exc:
        logger.exception("%s serviceability request failed", _aggregator_label)
        return {"aggregator": _aggregator_label, "couriers": [], "error": str(exc)}

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not response.ok:
        return {
            "aggregator": _aggregator_label,
            "couriers": [],
            "error": data or response.text,
        }

    requested = {
        _normalize_name(name) for name in (couriers or []) if _normalize_name(name)
    }

    results = []
    for item in _extract_serviceability_items(data):
        name = item.get("courier_name") or item.get("courier") or item.get("name")
        if not name:
            continue
        normalized = _normalize_name(str(name))
        if requested and normalized not in requested:
            continue

        results.append(
            {
                "name": str(name).strip(),
                "courier_code": item.get("courier_code") or item.get("code"),
                "serviceable": item.get("serviceable", True),
                "eta": item.get("etd") or item.get("estimated_days"),
                "type": item.get("type") or item.get("mode"),
            }
        )

    return {"aggregator": _aggregator_label, "couriers": results}
