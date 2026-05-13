import json
import logging
from typing import Dict, Any, Optional, Tuple

import requests
from django.conf import settings

from account import creds
from purple_drone_integration import common

logger = logging.getLogger("my-logger")


# Base request function
def pd_request(
    request_method: str,
    payload: Optional[Any],
    action_url: str,
    headers: Optional[dict] = None,
    base_url: str = None,
    content_type: str = "application/json",
    is_token_required: bool = True,
    retry_count: int = 0,
    max_retries: int = 2,
) -> requests.Response:
    """
    Robust PurpleDrone request:
      - Attaches Authorization header (strips token).
      - Adds Accept header.
      - Detects 401/403 and 'detail' error and will refresh token once and retry.
    """
    base_url = base_url or getattr(
        settings, "PURPLEDRONE_HOST", "https://backend-uat.fulfillzy.com"
    )
    url = f"{base_url.rstrip('/')}{action_url}"
    headers = headers.copy() if headers else {}
    headers.setdefault("Content-Type", content_type)
    headers.setdefault("Accept", "application/json")

    if is_token_required:
        token = creds.PURPLEDRONE_BLUEDART_AIR_500GM_TOKEN
        if token:
            token = token.strip()
            headers["Authorization"] = token

    data = payload
    if payload is not None and not isinstance(payload, str):
        data = json.dumps(payload)

    try:
        res = requests.request(
            method=request_method.upper(),
            url=url,
            headers=headers,
            data=data,
            timeout=(10, 30),
        )
    except requests.exceptions.RequestException as e:
        logger.exception("PurpleDrone request exception for %s: %s", url, e)
        raise

    # Log raw response for debugging
    try:
        res_json = res.json()
        logger.info(f"PurpleDrone Response for {action_url}: {res_json}")
    except Exception:
        logger.info(
            f"PurpleDrone raw response (non-json) for {url}: status={res.status_code} text={res.text[:400]}"
        )
        return res

    # If response indicates auth failure (HTTP 401/403 or detail errors), try regenerating token once and retry
    if (res.status_code in (401, 403)) or (
        isinstance(res_json, dict)
        and ("detail" in res_json and "auth" in str(res_json.get("detail", "")).lower())
    ):
        logger.warning(
            "PurpleDrone auth failure detected for %s: status=%s detail=%s",
            action_url,
            res.status_code,
            res_json.get("detail"),
        )
        if retry_count < max_retries:
            try:
                logger.info(
                    "Refreshing PurpleDrone token and retrying (attempt %s)...",
                    retry_count + 1,
                )
                generate_token(
                    creds.PURPLEDRONE_BLUEDART_AIR_500GM_USERNAME,
                    creds.PURPLEDRONE_BLUEDART_AIR_500GM_PASSWORD,
                )
            except Exception:
                logger.exception("Failed to refresh PurpleDrone token")
                return res
            # retry once with refreshed token
            return pd_request(
                request_method=request_method,
                payload=payload,
                action_url=action_url,
                headers=headers,
                base_url=base_url,
                content_type=content_type,
                is_token_required=is_token_required,
                retry_count=retry_count + 1,
                max_retries=max_retries,
            )

    return res


# Authentication
def generate_token(username: str, password: str) -> requests.Response:
    """
    Call /authToken to obtain token. Stores token in creds.PURPLEDRONE_TOKEN if successful.
    """
    host = getattr(settings, "PURPLEDRONE_HOST", "https://backend-uat.fulfillzy.com")
    action = "/authToken"
    payload = {"username": username, "password": password}

    res = pd_request("POST", payload, action, is_token_required=False, base_url=host)
    try:
        res_json = res.json()
    except Exception:
        logger.error(
            "PurpleDrone generate_token: invalid/non-json response: %s",
            getattr(res, "text", ""),
        )
        return res

    status = str(res_json.get("status", "")).upper()
    # token may be in res_json['token'] or res_json['token'] nested inside other keys
    token = res_json.get("token") or res_json.get("access_token") or None
    if not token and isinstance(res_json.get("data"), dict):
        token = res_json["data"].get("token") or res_json["data"].get("access_token")
    if not token and isinstance(res_json.get("data"), str):
        token_candidate = res_json.get("data")
        if isinstance(token_candidate, str) and token_candidate.count(".") == 2:
            token = token_candidate

    if status == "SUCCESS" and token:
        token = token.strip()
        creds.PURPLEDRONE_BLUEDART_AIR_500GM_TOKEN = token
        logger.info(
            "PurpleDrone token refreshed and saved to creds.PURPLEDRONE_BLUEDART_AIR_500GM_TOKEN (masked)."
        )
    elif token:
        # sometimes API returns token but no status
        token = token.strip()
        creds.PURPLEDRONE_BLUEDART_AIR_500GM_TOKEN = token
        logger.info("PurpleDrone token set from response (no SUCCESS status).")
    else:
        logger.error("PurpleDrone token generation failed: %s", res_json)

    return res


# Waybill generation (order booking)
def order_booking(shipment_data: Dict[str, Any]) -> requests.Response:
    common.order_booking(shipment_data, pd_request)


# Cancel order (POST /cancel)
# def cancel_order(waybill: str) -> requests.Response:
#     return pd_request("POST", {"waybill": waybill}, "/cancel", headers={})


# Cancel order (POST /cancel)
def cancel_shipment(waybill: str) -> requests.Response:
    return common.cancel_shipment(waybill, pd_request)


# Track / fetch order status
def track_shipment(awb_number: str) -> requests.Response:
    """
    GET /api/orders?query_type=track&query_value=<awb>
    """
    return common.track_shipment(awb_number, pd_request)


# Ship order interface used by central task (same return shape as xpressbees.ship_order)
def ship_order(
    order, hub, return_shipment: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Ship an order via PurpleDrone API.
    Returns (True, response_json) on success; (False, {"error": msg, "response": res_json}) on failure.
    """
    return common.ship_order(order, hub, "pd_bd_a_500", pd_request, return_shipment)
