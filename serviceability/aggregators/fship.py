"""Fship serviceability adapter for the serviceability app.

Kept self-contained here (rather than in ``fship_integration.common``) so the
serviceability feature never touches the shipping-critical carrier modules. It
reuses only the low-level authenticated request helper from that module.
"""

import logging
from collections.abc import Callable
from typing import Optional

from fship_integration.common import fship_request

logger = logging.getLogger("my-logger")


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _extract_serviceability_items(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    for key in ["serviceable_courier_list", "courier_list", "couriers"]:
        items = payload.get(key)
        if isinstance(items, list):
            return items

    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["serviceable_courier_list", "courier_list", "couriers"]:
            items = data.get(key)
            if isinstance(items, list):
                return items

    return []


def _is_route_serviceable(payload: dict) -> bool:
    """Fship often returns route-level flags without a per-courier list."""
    if not isinstance(payload, dict):
        return False
    status = payload.get("status")
    if status not in (True, "true", "True", 1, "1"):
        return False
    pickup = str(payload.get("pickup", "")).strip().lower()
    delivery = str(payload.get("delivery", "")).strip().lower()
    return pickup == "yes" and delivery == "yes"


def check_serviceability(
    pickup_pincode: str,
    destination_pincode: str,
    couriers: Optional[list[str]] = None,
    fs_request: Callable = fship_request,
) -> dict:
    payload = {
        "source_Pincode": str(pickup_pincode),
        "destination_Pincode": str(destination_pincode),
    }

    try:
        response = fs_request("POST", payload, "/pincodeserviceability")
    except Exception as exc:
        logger.exception("Fship serviceability request failed")
        return {"aggregator": "Fship", "couriers": [], "error": str(exc)}

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not response.ok:
        return {"aggregator": "Fship", "couriers": [], "error": data or response.text}

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
                "eta": item.get("eta") or item.get("estimated_days"),
                "type": item.get("type") or item.get("mode"),
            }
        )

    if not results and _is_route_serviceable(data) and couriers:
        for name in couriers:
            label = str(name).strip()
            if not label:
                continue
            if requested and _normalize_name(label) not in requested:
                continue
            results.append(
                {
                    "name": label,
                    "serviceable": True,
                    "type": "surface",
                }
            )

    return {"aggregator": "Fship", "couriers": results}
