from collections.abc import Callable
import json
import logging
from datetime import datetime
import random
from typing import Dict, Any, Optional

import requests
from requests import Response

from account import creds
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from account.models import Courier
from order_manager.models import Hub, Order, OrderItem

logger = logging.getLogger("my-logger")

OAUTH_URL = "https://oauth.smartship.in"
BASE_URL = "https://api.smartship.in"


# ==========================================================
# SESSION MANAGEMENT
# ==========================================================
def create_session() -> requests.Session:
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )

    adapter = HTTPAdapter(
        max_retries=retries,
        pool_connections=50,
        pool_maxsize=50,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )

    return session


SESSION = create_session()


# ==========================================================
# TOKEN MANAGEMENT
# SmartShip uses OAuth2 Bearer tokens (valid for 1 hour).
# Call refresh_smartship_token() to obtain a fresh token and
# store it in creds.SMARTSHIP_TOKEN / creds.SMARTSHIP_REFRESH_TOKEN.
# ==========================================================
def refresh_smartship_token() -> bool:
    """
    Obtain a new access token using the Login Token API.
    Stores the token in creds.SMARTSHIP_TOKEN.
    Returns True on success, False on failure.

    Required creds attributes:
        SMARTSHIP_USERNAME     - account email
        SMARTSHIP_PASSWORD_MD5 - MD5 hash of the account password
        SMARTSHIP_CLIENT_ID    - client_id from API Credentials tab
        SMARTSHIP_CLIENT_SECRET- client_secret from API Credentials tab
    """
    payload = {
        "username": creds.SMARTSHIP_USERNAME,
        "password": creds.SMARTSHIP_PASSWORD_MD5,  # MD5 hash
        "client_id": creds.SMARTSHIP_CLIENT_ID,
        "client_secret": creds.SMARTSHIP_CLIENT_SECRET,
        "grant_type": "password",
    }
    try:
        res = SESSION.post(
            f"{OAUTH_URL}/loginToken.php",
            data=json.dumps(payload),
            timeout=(5, 20),
        )
        data = res.json()
        if "access_token" in data:
            creds.SMARTSHIP_TOKEN = data["access_token"]
            creds.SMARTSHIP_REFRESH_TOKEN = data.get("refresh_token", "")
            logger.info("SmartShip token refreshed successfully.")
            return True
        else:
            logger.error("SmartShip token refresh failed: %s", data)
            return False
    except Exception:
        logger.exception("SmartShip token refresh exception")
        return False


def smartship_request(
    method: str,
    payload: Optional[Any],
    action_url: str,
    headers: Optional[dict] = None,
    is_token_required: bool = True,
    base: str = BASE_URL,
) -> requests.Response:
    global SESSION

    url = f"{base.rstrip('/')}{action_url}"
    headers = headers.copy() if headers else {}
    data = payload if isinstance(payload, str) else json.dumps(payload)

    def _set_auth():
        """Always reads the latest token from creds."""
        if is_token_required and getattr(creds, "SMARTSHIP_TOKEN", None):
            headers["Authorization"] = f"Bearer {creds.SMARTSHIP_TOKEN.strip()}"

    def _do_request():
        logger.debug(f"SmartShip:: Making request: {url}. Data: {data}")
        res = SESSION.request(
            method=method.upper(),
            url=url,
            headers=headers,
            data=data,
            timeout=(5, 20),
        )
        logger.debug(f"SmartShip:: Res Json: {res.json()}")
        return res

    _set_auth()

    # ── Attempt 1: normal request ──────────────────────────────────────────
    try:
        res = _do_request()
    except requests.exceptions.RequestException as e:
        # Session is dead → recreate it, refresh token, then try once more
        logger.warning(
            "SmartShip session error: %s. Recreating session + refreshing token.", e
        )
        SESSION = create_session()
        refresh_smartship_token()
        _set_auth()
        try:
            return _do_request()
        except Exception:
            logger.exception("SmartShip request failed after session reset -> %s", url)
            raise

    # ── Attempt 2: token expired (HTTP 401/403) ────────────────────────────
    if res.status_code in (401, 403) or str(res.json().get("status")) in ("401", "403"):
        logger.warning(
            "SmartShip token expired (HTTP %s). Refreshing token...", res.status_code
        )
        if not refresh_smartship_token():
            logger.error(
                "SmartShip token refresh failed. Returning original %s response.",
                res.status_code,
            )
            return res  # propagate auth failure to caller — don't loop forever
        _set_auth()

        # After token refresh the session itself might also have gone stale
        try:
            res = _do_request()
        except requests.exceptions.RequestException as e:
            logger.warning(
                "SmartShip session died after token refresh: %s. Recreating session.", e
            )
            SESSION = create_session()
            try:
                res = _do_request()
            except Exception:
                logger.exception(
                    "SmartShip request failed after token refresh + session reset -> %s",
                    url,
                )
                raise

    return res


# ==========================================================
# PAYLOAD BUILDER
# Converts an internal Order into the SmartShip
# orderRegistrationOneStep / orderRegistration payload format.
# ==========================================================
def build_payload(
    order: Order,
    hub: Hub,
    warehouse_id: int,
    courier_id: int,
    ss_request: Callable = smartship_request,
    shipment_weight: float | None = None,
    mode="surface",  # kept for API-compatibility; not used by SmartShip
    preferred_carriers: list[int] | None = None,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict]]:
    """
    Build a SmartShip One-Step order payload.

    Weight conversion: internal value is in kg → SmartShip expects grams.
    Dimensions stay in centimetres (same as SmartShip).
    """
    weight_kg = (
        order.shipment.package_weight_kg if shipment_weight is None else shipment_weight
    )
    weight_grams = int(float(weight_kg) * 1000)

    is_cod = order.payment.method == "cod"
    payment_type = "cod" if is_cod else "prepaid"
    collectable_amount = str(order.total_amount) if is_cod else "0"

    # Build product_details list
    product_details = []
    for item in OrderItem.objects.filter(order=order):
        product_details.append(
            {
                "client_product_reference_id": str(item.sku_code or item.id),
                "product_name": item.product.name,
                "product_category": "",  # fill in if available
                "product_hsn_code": "",  # fill in if available
                "product_quantity": str(item.quantity),
                "product_invoice_value": str(item.unit_price),
                "product_gst_tax_rate": "",
                "product_taxable_value": str(item.unit_price),
                "product_sgst_amount": "",
                "product_sgst_tax_rate": "",
                "product_cgst_amount": "",
                "product_cgst_tax_rate": "",
            }
        )

    order_meta: Dict[str, Any] = {}
    if preferred_carriers:
        order_meta["preferred_carriers"] = preferred_carriers

    payload = {
        "request_info": {
            "client_id": getattr(creds, "SMARTSHIP_CLIENT_ID", ""),
            "run_type": "create",
        },
        "orders": [
            {
                "client_order_reference_id": f"{order.get_order_id()}-{random.randint(100000, 999999)}",
                "shipment_type": 1,  # 1 = forward
                "order_collectable_amount": collectable_amount,
                "total_order_value": str(order.total_amount),
                "payment_type": payment_type,
                "package_order_weight": str(weight_grams),
                "package_order_length": str(order.shipment.package_length_cm),
                "package_order_height": str(order.shipment.package_height_cm),
                "package_order_width": str(order.shipment.package_width_cm),
                "shipper_hub_id": str(warehouse_id),
                "shipper_gst_no": getattr(hub, "gst_no", "") or "",
                "order_invoice_date": datetime.now().strftime("%d-%m-%Y"),
                "order_invoice_number": order.get_order_id(),
                "order_meta": {"preferred_carriers": [courier_id]},
                **({"order_meta": order_meta} if order_meta else {}),
                "product_details": product_details,
                "consignee_details": {
                    "consignee_name": order.shipping_address.name,
                    "consignee_phone": order.shipping_address.phone,
                    "consignee_email": order.shipping_address.email
                    or "support@idiotship.tech",
                    "consignee_complete_address": " ".join(
                        filter(
                            None,
                            [
                                order.shipping_address.line1,
                                order.shipping_address.landmark,
                            ],
                        )
                    ),
                    "consignee_pincode": order.shipping_address.pin_code,
                },
            }
        ],
    }

    return payload, None


# ==========================================================
# PICKUP LOCATION (WAREHOUSE / HUB)
# ==========================================================
def list_warehouse(
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Fetch all registered hubs.
    Pass empty string to get all hubs (SmartShip behaviour for hub_ids="").
    """
    return ss_request(
        "POST", {"hub_ids": ""}, "/v2/app/Fulfillmentservice/getHubDetail"
    )


def create_warehouse(
    hub: Hub,
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Register a new hub (pickup location) with SmartShip.

    SmartShip response on success:
        {"status": 1, "data": {"info": "Hub registered successfully", "hub_id": 1239}}
    """
    payload = {
        "hub_details": {
            "hub_name": hub.name,
            "pincode": hub.pin_code,
            "city": hub.city,
            "state": getattr(hub, "state", ""),
            "address1": hub.address_line1,
            "address2": hub.address_line2 or "",
            "hub_phone": hub.phone,
            "delivery_type_id": 2,  # 1=Express, 2=Economy, 3=Bulk
        }
    }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/hubRegistration")


def remove_warehouse(
    warehouse_id: int,
    ss_request: Callable = smartship_request,
) -> Response:
    """Delete a hub by its SmartShip hub_id."""
    return ss_request(
        "POST",
        {"hub_ids": [warehouse_id]},
        "/v2/app/Fulfillmentservice/deleteHub",
    )


def update_warehouse(
    warehouse_id: int,
    hub: Hub,
    ss_request: Callable = smartship_request,
) -> Response:
    """Update an existing hub's details."""
    payload = {
        "hub_id": str(warehouse_id),
        "hub_name": hub.name,
        "hub_phone": hub.phone,
        "pincode": hub.pin_code,
        "city": hub.city,
        "state": getattr(hub, "state", ""),
        "address1": hub.address_line1,
        "address2": hub.address_line2 or "",
    }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/updateHubDetails")


# ==========================================================
# SHIPMENT
# ==========================================================
def order_booking(
    shipment_data: Dict[str, Any],
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Register an order using the One-Step API (≤10 orders).
    Returns AWB number, label URL, and carrier info in a single call.
    """
    return ss_request(
        "POST",
        shipment_data,
        "/v2/app/Fulfillmentservice/orderRegistrationOneStep",
    )


def order_booking_bulk(
    shipment_data: Dict[str, Any],
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Register orders via the background batch API (no order limit).
    AWB assignment happens asynchronously - poll get_order_details() to confirm.
    """
    return ss_request(
        "POST",
        shipment_data,
        "/v2/app/Fulfillmentservice/orderRegistration",
    )


def get_order_details(
    client_order_reference_ids: list[str] | None = None,
    request_order_ids: list[str] | None = None,
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Fetch order details / status from SmartShip.
    Use this to poll for AWB assignment after order_booking_bulk().
    """
    filters: Dict[str, Any] = {}
    if client_order_reference_ids:
        filters["client_order_reference_id"] = ",".join(client_order_reference_ids)
    if request_order_ids:
        filters["request_order_id"] = ",".join(str(i) for i in request_order_ids)

    payload = {
        "filters": {"filter_type": {"and": filters}},
        "limit": {"offset": 0, "limit": 50},
    }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/orderDetails")


def assign_awb(
    shipment_id: int,
    ss_request: Callable = smartship_request,
    courier_id: Optional[int] = None,
) -> Response:
    """
    SmartShip handles AWB assignment automatically during order registration.
    This stub is retained for interface compatibility; call get_order_details()
    to retrieve the assigned AWB for background-registered orders.
    """
    return get_order_details(
        request_order_ids=[str(shipment_id)], ss_request=ss_request
    )


def track_shipment(
    awb_number: str,
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Track a SmartShip order by AWB (tracking_number).
    SmartShip tracking API is a GET request with a query param.
    """
    global SESSION
    url = f"{BASE_URL}/v1/Trackorder"
    headers = {}
    if creds.SMARTSHIP_TOKEN:
        headers["Authorization"] = f"Bearer {creds.SMARTSHIP_TOKEN.strip()}"
        headers["Content-Type"] = "application/json"

    try:
        return SESSION.get(
            url,
            params={"tracking_numbers": awb_number},
            headers=headers,
            timeout=(5, 20),
        )
    except requests.exceptions.RequestException:
        logger.exception("SmartShip track_shipment failed for AWB %s", awb_number)
        raise


def cancel_shipment(
    awb_number: str,
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Cancel a SmartShip order by client_order_reference_id.
    """
    order = Order.objects.get(awb_number=awb_number)
    req_order_id = order.json.get("smartship_request_order_id", "")
    payload = {
        "request_info": {},
        "orders": {
            "request_order_ids": [req_order_id],
        },
    }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/orderCancellation")


def cancel_bulk_orders(orders: list[Order], ss_request: Callable = smartship_request):
    """Bulk cancel orders by iterating and calling cancel_shipment for each."""
    payload = {
        "request_info": {},
        "orders": {
            "request_order_ids": [
                o.json.get("smartship_request_order_id", "") for o in orders
            ],
        },
    }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/orderCancellation")


def get_courier_list(
    ss_request: Callable = smartship_request,
) -> Response:
    """
    SmartShip doesn't expose a 'list carriers' endpoint directly.
    Use the Hub Serviceability API to get available carriers for a hub/pincode.
    This stub returns serviceability info for all preferred carriers.
    """
    raise NotImplementedError(
        "SmartShip does not have a direct 'get all couriers' endpoint. "
        "Use check_serviceability() with your hub_id and destination pincode instead."
    )


def check_serviceability(
    hub_id: int,
    destination_pincode: int,
    order_weight: int = 500,
    preferred_carriers: list[int] | None = None,
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Check carrier serviceability for a hub → pincode route.
    Returns available carriers and cost estimates.
    """
    payload: Dict[str, Any] = {
        "order_info": {
            "hub_ids": [hub_id],
            "destination_pincode": destination_pincode,
            "order_weight": order_weight,
        },
        "request_info": {
            "extra_info": True,
            "cost_info": True,
        },
    }
    if preferred_carriers:
        payload["order_info"]["preferred_carriers"] = preferred_carriers

    return ss_request(
        "POST", payload, "/v2/app/Fulfillmentservice/ServiceabilityHubWise"
    )


# ==========================================================
# MANIFEST
# SmartShip requires a manifest to be created before pickup.
# This replaces fship's register_pickup().
# ==========================================================
def register_pickup(
    client_order_reference_ids: list[str],
    ss_request: Callable = smartship_request,
    preferred_pickup_date: str = "",
) -> Response:
    """
    Create a manifest for the given orders (equivalent to register_pickup in fship).
    preferred_pickup_date format: "YYYY-MM-DD" or leave empty for default.
    """
    payload = {
        "client_order_reference_ids": client_order_reference_ids,
        "preferred_pickup_date": preferred_pickup_date,
        "shipment_type": 1,
    }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/createManifest")


# ==========================================================
# NDR (Non-Delivery Report)
# ==========================================================
def get_ndr_list(
    ss_request: Callable = smartship_request,
    ndr_type="initiated",
    from_date=None,
    to_date=None,
) -> Response:
    """
    Fetch NDR orders via Get Order Details API filtered by NDR-related status codes.
    SmartShip NDR status codes: 12-18, 22, 23 (delivery attempted / refused).
    """
    ndr_status_codes = "12,13,14,15,16,17,22,23"
    payload: Dict[str, Any] = {
        "filters": {
            "filter_type": {
                "and": {
                    "status": {
                        "status_code": ndr_status_codes,
                        "check_type": "Y",
                    }
                }
            }
        },
        "limit": {"offset": 0, "limit": 100},
    }
    if from_date and to_date:
        payload["filters"]["filter_type"]["and"]["updated_date"] = {
            "from": str(from_date),
            "to": str(to_date),
        }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/orderDetails")


def create_ndr_actions(
    request_order_id: str,
    action: int = 1,
    comments: str = "The Buyer does not want the product",
    next_attempt_date: str = "",
    address: str = "",
    phone: str = "",
    name: str = "",
    ss_request: Callable = smartship_request,
) -> Response:
    """
    Submit an NDR action for an order.
    action: 1 = reattempt delivery, 2 = RTO
    next_attempt_date: "YYYY-MM-DD" (required; must be within next 10 days)
    """
    payload = {
        "orders": [
            {
                "request_order_id": str(request_order_id),
                "action_id": str(action),
                "comments": comments,
                "next_attempt_date": next_attempt_date,
                "client_order_reference_id": [""],
                "address": address,
                "phone": phone,
                "names": name,
                "alternate_address": "",
                "alternate_number": "",
            }
        ]
    }
    return ss_request("POST", payload, "/v2/app/Fulfillmentservice/orderReattempt")


# ==========================================================
# LABEL GENERATION
# ==========================================================
def generate_label(
    orders: list[Order],
    ss_request: Callable = smartship_request,
) -> tuple[Exception | bool, list[str] | None]:
    """
    Fetch shipping label URLs for the given orders.
    Uses client_order_reference_ids (comma-separated).
    """
    ref_ids = ",".join(o.get_order_id() for o in orders if o.get_order_id())
    if not ref_ids:
        return True, ValueError("No valid order reference IDs found")

    res = ss_request(
        "POST",
        {"client_order_ref_id": ref_ids},
        "/v2/app/Fulfillmentservice/getShippingLabels",
    )
    try:
        res_json = res.json()
    except Exception:
        return True, ValueError("Failed to parse label response")

    if res_json.get("status") == 1:
        url = res_json.get("data", {}).get("url")
        # Also check one-step response format (label_url inside shipping_info)
        if not url:
            url = (
                res_json.get("data", {})
                .get("success_order_details", {})
                .get("shipping_info", {})
                .get("label_url")
            )
        if url:
            return False, [url]

    return True, ValueError("Label URL not found in response")


# ==========================================================
# HIGH-LEVEL ORCHESTRATION
# ==========================================================
def ship_order(
    order: Order,
    hub: Hub,
    courier_abbreviation: str,
    courier_id: str,
    return_shipment: bool = False,
    ss_request: Callable = smartship_request,
    shipment_weight: float | None = None,
    preferred_carriers: list[int] | None = None,
):
    """
    Full order-shipping flow:
      1. Ensure hub is registered in SmartShip.
      2. Build and submit the One-Step order payload.
      3. Extract AWB from the response.
      4. Create a manifest (replaces register_pickup).
      5. Persist order state.

    Returns (True, awb_number) on success or (False, {"error": ...}) on failure.
    """
    try:
        # ---- 1. Ensure hub exists in SmartShip ----
        warehouse_id = hub.json.get("smartship_hub_id")
        if not warehouse_id:
            res_json = create_warehouse(hub, ss_request).json()
            if res_json.get("status") != 1:
                err_info = (
                    res_json.get("data", {})
                    .get("message", {})
                    .get("info", "Unknown error")
                )
                return False, {"error": err_info}
            warehouse_id = res_json["data"]["hub_id"]
            hub.json["smartship_hub_id"] = warehouse_id
            hub.save()

        # ---- 2. Build payload ----
        payload, error = build_payload(
            order,
            hub,
            warehouse_id,
            courier_id,
            ss_request,
            shipment_weight=shipment_weight,
            preferred_carriers=[courier_id],
        )
        if not payload:
            return False, {
                "error": f"Failed to build payload. Error: {error.get('error')}"
            }

        # ---- 3. Book order ----
        res_json = order_booking(payload, ss_request).json()

        if res_json.get("status") != 1:
            return False, {"error": res_json.get("message", "Unknown error")}

        # Extract first order result from success_order_details
        success_orders = (
            res_json.get("data", {}).get("success_order_details", {}).get("orders", [])
        )
        if not success_orders:
            return False, {"error": "No success order details returned by SmartShip"}

        order_result = success_orders[0]
        awb_no = order_result.get("awb_number")
        if not awb_no:
            return False, {
                "error": f"AWB not assigned yet. Order state code: {order_result.get('code')}. "
                "Use get_order_details() to poll for AWB assignment."
            }

        order.json["order_creating_response"] = res_json
        order.json["smartship_request_order_id"] = order_result.get("request_order_id")

        # ---- 4. Create manifest (replaces register_pickup) ----
        manifest_res = register_pickup([order.get_order_id()], ss_request).json()
        order.json["manifest_response"] = manifest_res

        # ---- 5. Persist ----
        order.awb_number = awb_no
        order.route_code = order_result.get("route_code", "")
        order.hub = hub
        order.logistic_partner = Courier.objects.get(abbreviation=courier_abbreviation)
        order.update_status("pending_pickup")
        order.save()

        return True, order.awb_number

    except Exception as e:
        logger.exception("SmartShip ship_order exception")
        return False, {"error": str(e)}


def bulk_ship_orders(
    orders: list[Order],
    hub: Hub,
    courier_abbreviation: str,
    courier_id: str,
    shipment_weight: float | None = None,
    preferred_carriers: list[int] | None = None,
):
    """
    Bulk order shipping flow using SmartShip's One-Step API.
    Orders are processed individually (One-Step limit is 10 per call;
    batching is done here to stay within that limit).

    Returns a results dict with success_orders / failed_orders lists.
    """
    results = {
        "success_orders": [],
        "failed_orders": [],
        "error": None,
    }

    courier = Courier.objects.get(abbreviation=courier_abbreviation)

    # ---- Ensure hub is registered ----
    warehouse_id = hub.json.get("smartship_hub_id")
    if not warehouse_id:
        res = create_warehouse(hub).json()
        if res.get("status") != 1:
            err_info = (
                res.get("data", {}).get("message", {}).get("info", "Unknown error")
            )
            results["error"] = err_info
            return results

        warehouse_id = res["data"]["hub_id"]
        hub.json["smartship_hub_id"] = warehouse_id
        hub.save(update_fields=["json"])

    orders = orders.select_related("shipping_address", "payment", "shipment")
    orders = list(orders)

    successful_client_ids = []
    success_orders = []

    # ---- Main loop ----
    for order in orders:
        try:
            payload, err = build_payload(
                order,
                hub,
                warehouse_id,
                courier_id,
                shipment_weight=shipment_weight,
                preferred_carriers=preferred_carriers,
            )
            if not payload:
                results["failed_orders"].append(
                    (order.id, f"Failed to build payload. Error: {err.get('error')}")
                )
                order.update_status("ready_to_ship")
                continue

            res_json = order_booking(payload).json()
            res_json_data = res_json.get("data", {})

            if res_json.get("status") != 1:
                results["failed_orders"].append(
                    (order.id, res_json.get("message", "Unknown error"))
                )
                order.update_status("ready_to_ship")
                continue

            if not res_json_data.get("total_success_orders"):
                results["failed_orders"].append(
                    (order.id, "No success order details returned")
                )
                order.update_status("ready_to_ship")
                continue

            success_order_list = res_json_data.get("success_order_details", {}).get(
                "orders", []
            )
            if not success_order_list:
                results["failed_orders"].append(
                    (order.id, "No success order details returned")
                )
                order.update_status("ready_to_ship")
                continue

            try:
                if success_order_list[0].get("code") != 4:
                    results["failed_orders"].append(
                        (order.id, "Pincode not servicable")
                    )
                    order.update_status("ready_to_ship")
                    continue
            except:
                results["failed_orders"].append((order.id, "Pincode not servicable"))
                order.update_status("ready_to_ship")
                continue

            order_result = success_order_list[0]
            awb = order_result.get("awb_number")

            if not awb:
                # AWB not yet assigned (background processing) - still consider partial success
                logger.warning(
                    "Order %s registered but AWB not yet assigned (code=%s). "
                    "Poll get_order_details() later.",
                    order.id,
                    order_result.get("code"),
                )

            order.json["order_creating_response"] = res_json
            order.json["smartship_request_order_id"] = order_result.get(
                "request_order_id"
            )
            order.awb_number = awb or ""
            order.hub = hub
            order.logistic_partner = courier
            order.route_code = order_result.get("route_code", "")
            order.update_status("pending_pickup")
            order.save(
                update_fields=[
                    "json",
                    "awb_number",
                    "hub",
                    "logistic_partner",
                    "status",
                ]
            )

            successful_client_ids.append(order.get_order_id())
            success_orders.append(order)
            results["success_orders"].append((order.id, res_json))

        except Exception as e:
            logger.exception("SmartShip bulk ship error for order %s", order.id)
            results["failed_orders"].append((order.id, str(e)))

    # ---- Bulk manifest (replaces bulk register_pickup) ----
    if successful_client_ids:
        try:
            manifest_res = register_pickup(successful_client_ids).json()
            # Persist manifest response on each success order
            for o in success_orders:
                o.json["manifest_response"] = manifest_res
                o.save(update_fields=["json"])
        except Exception:
            logger.exception("SmartShip error while creating manifest for bulk orders")

    return results
