from collections.abc import Callable
import json
import logging
from typing import Dict, Any, Optional

import requests
from requests import Response

from account import creds
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from account.models import Courier
from order_manager.models import Hub, Order, OrderItem


logger = logging.getLogger("my-logger")
base_url = "https://capi.fship.in/api"


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
# BASE REQUEST
# ==========================================================
def fship_request(
    method: str,
    payload: Optional[Any],
    action_url: str,
    headers: Optional[dict] = None,
    is_token_required: bool = True,
) -> requests.Response:

    global SESSION

    url = f"{base_url.rstrip('/')}{action_url}"
    headers = headers.copy() if headers else {}

    if is_token_required and creds.FSHIP_TOKEN:
        headers.setdefault("signature", creds.FSHIP_TOKEN.strip())

    data = payload if isinstance(payload, str) else json.dumps(payload)

    try:
        logger.debug(f"Making FS Request: {url}")
        res = SESSION.request(
            method=method.upper(),
            url=url,
            headers=headers,
            data=data,
            timeout=(5, 20),
        )
        logger.debug(f"FS Response: {res.json()}")

        # ⭐ Handle token expiry automatically
        if res.status_code in [401, 403]:
            logger.warning("Fship token expired or unauthorized. Retrying once...")

            # 👉 If you have token refresh logic, call it here
            # refresh_fship_token()

            headers["signature"] = creds.FSHIP_TOKEN.strip()

            res = SESSION.request(
                method=method.upper(),
                url=url,
                headers=headers,
                data=data,
                timeout=(5, 20),
            )

        return res

    except requests.exceptions.RequestException as e:
        logger.warning("Session possibly dead. Recreating session...")

        # ⭐ Recreate session automatically
        SESSION = create_session()

        try:
            return SESSION.request(
                method=method.upper(),
                url=url,
                headers=headers,
                data=data,
                timeout=(5, 20),
            )
        except Exception:
            logger.exception("Fship request failed after session reset -> %s", url)
            raise


# ==========================================================
# PAYLOAD BUILDER
# ==========================================================
def build_payload(
    order: Order,
    hub: Hub,
    warehouse_id: int,
    courier_id: int,
    fs_request: Callable = fship_request,
    shipment_weight: float | None = None,
    mode="surface",
) -> Optional[Dict[str, Any]]:
    items = []
    for item in OrderItem.objects.filter(order=order):
        items.append(
            {
                "productName": item.product.name,
                "unitPrice": item.unit_price,
                "quantity": item.quantity,
                "sku": item.sku_code,
            }
        )

    payload = {
        "customer_Name": order.shipping_address.name,
        "customer_Mobile": order.shipping_address.phone,
        "customer_Emailid": order.shipping_address.email or "support@idiotship.tech",
        "customer_Address": order.shipping_address.line1,
        "landMark": order.shipping_address.landmark,
        "customer_Address_Type": order.shipping_address.label or "Home",
        "customer_PinCode": order.shipping_address.pin_code,
        "customer_City": order.shipping_address.city,
        "orderId": order.get_order_id_for_aggregator(),
        "payment_Mode": 1 if order.payment.method == "cod" else 2,
        "express_Type": mode,
        "is_Ndd": 0,
        "order_Amount": order.total_amount,
        "tax_Amount": 0,
        "extra_Charges": 0,
        "total_Amount": order.total_amount,
        "cod_Amount": order.total_amount if order.payment.method == "cod" else 0,
        "shipment_Weight": (
            order.shipment.package_weight_kg
            if shipment_weight is None
            else shipment_weight
        ),
        "shipment_Length": order.shipment.package_length_cm,
        "shipment_Width": order.shipment.package_width_cm,
        "shipment_Height": order.shipment.package_height_cm,
        "products": items,
        # "volumetric_Weight": 0,
        # "latitude": 0,
        # "longitude": 0,
        "pick_Address_ID": warehouse_id,
        # "return_Address_ID": 0,
        "courierId": courier_id,
    }
    return payload, None


# ==========================================================
# PICKUP LOCATION (WAREHOUSE)
# ==========================================================
def list_warehouse(
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
) -> Response:
    raise NotImplementedError()


def create_warehouse(
    hub: Hub,
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
) -> Response:
    payload = {
        "warehouseName": hub.name,
        "contactName": hub.contact_person,
        "addressLine1": hub.address_line1,
        "addressLine2": hub.address_line2,
        "pincode": hub.pin_code,
        "city": hub.city,
        "phoneNumber": hub.phone,
        "email": hub.email,
    }
    return fs_request(
        "POST",
        json.dumps(payload),
        "/addwarehouse",
    )


def remove_warehouse(
    warehouse_id: int,
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
) -> Response:
    raise NotImplementedError()


# ==========================================================
# SHIPMENT
# ==========================================================
def order_booking(
    shipment_data: Dict[str, Any],
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
) -> Response:
    return fs_request(
        "POST",
        json.dumps(shipment_data),
        "/createforwardorder",
    )


def assign_awb(
    shipment_id: int,
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
    courier_id: Optional[int] = None,
) -> Response:
    payload = {"shipment_id": shipment_id}

    if courier_id is not None:
        payload["courier_id"] = courier_id

    return fs_request(
        "POST",
        json.dumps(payload),
        "/courier/assign/awb",
    )


def track_shipment(
    awb_number: str,
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
) -> Response:
    payload = {"waybill": str(awb_number)}
    return fs_request(
        "POST",
        payload,
        "/trackinghistory",
    )


def cancel_shipment(
    awb_number: str,
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
) -> Response:
    return fs_request(
        "POST",
        json.dumps({"waybill": str(awb_number)}),
        "/cancelorder",
    )


def cancel_bulk_orders(orders: list[Order], hub = None):
    """Bulk cancel orders"""
    for o in orders:
        try:
            cancel_shipment(o.awb_number)
        except:
            pass


def get_courier_list(
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
    token: str = "",
) -> Response:
    return fs_request("GET", None, "/getallcourier")


# ==========================================================
# NDR
# ==========================================================
def get_ndr_list(
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
    ndr_type="initiated",
    from_date=None,
    to_date=None,
) -> Response:
    return fs_request("GET", None, "/ndr/all")


def create_ndr_actions(
    awb_no: str,
    fs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = fship_request,
) -> Response:
    return fs_request(
        "POST",
        json.dumps(
            {"action": "return", "comments": "The Buyer does not want the product"}
        ),
        f"/ndr/{awb_no}/action",
    )


def register_pickup(awbs: list[str], fs_request: Callable = fship_request) -> Response:
    return fs_request("POST", json.dumps({"waybills": awbs}), "/registerpickup")


# ==========================================================
# HIGH LEVEL ORCHESTRATION
# ==========================================================
def generate_label(
    orders: list[Order],
) -> tuple[Exception | bool, list[str] | None]:
    pickupOrderIds = []
    for i in orders:
        try:
            if (
                pickupOrderId := i.json.get("register_pickup", {})
                .get("apipickuporderids", [])[0]
                .get("pickupOrderId", "")
            ):
                if pickupOrderId:
                    pickupOrderIds.append(str(pickupOrderId))
        except:
            continue

    payload = {"pickupOrderId": pickupOrderIds}

    res_json = fship_request(
        "POST", json.dumps(payload), "/shippinglabelbypickupid"
    ).json()
    if res_json.get("status", "") == "Success":
        urls = []
        shipmentData = res_json.get("shipmentData", [])
        for i in shipmentData:
            url = i.get("labelfile")
            if url:
                urls.append(url)

        if urls:
            return False, urls

    return True, ValueError("Urls doesn't exists")


def ship_order(
    order: Order,
    hub: Hub,
    courier_abbreviation: str,
    courier_id: str,
    return_shipment: bool = False,
    fs_request: Callable = fship_request,
    shipment_weight: float | None = None,
):
    try:
        warehouse_id = hub.json.get("fship_hub_id")
        if not warehouse_id:
            res_json = create_warehouse(hub, fs_request).json()
            if not res_json.get("status"):
                return False, {
                    "error": res_json.get("response", "Unknown error")
                    .replace("at support@fship.in", "at support@idiotship.tech")
                    .replace("fship", "")
                }
            else:
                warehouse_id = res_json.get("warehouseId")
                hub.json["fship_hub_id"] = warehouse_id
                hub.save()

        payload, error = build_payload(
            order,
            hub,
            warehouse_id,
            courier_id,
            fs_request,
            shipment_weight=shipment_weight,
        )
        if not payload:
            return False, {
                "error": f"Failed to build payload. Error: {error.get('error')}"
            }


        res_json = order_booking(payload, fs_request).json()
        if not res_json.get("status") or "waybill" not in res_json:
            return False, {
                "error": res_json.get("response", "Unknown error")
                .replace("at support@fship.in", "at support@idiotship.tech")
                .replace("fship", "")
            }

        try:
            if res_json.get("errors"):
                for k, v in res_json.get("errors").items():
                    return False, {"errors": f"{k}: {','.join(v)}"}
        except:
            pass

        order.json |= {"order_creating_response": res_json}
        awb_no = res_json.get("waybill")

        res_json1 = register_pickup([awb_no], fs_request).json()

        order.json["register_pickup"] = res_json1

        order.awb_number = awb_no
        order.route_code = res_json.get("route_code", "")
        order.hub = hub
        order.logistic_partner = Courier.objects.get(abbreviation=courier_abbreviation)
        order.update_status("pending_pickup")
        order.save()

        return True, order.awb_number

    except Exception as e:
        logger.exception("Fship Ship Order Exception")
        return False, {"error": str(e)}


def bulk_ship_orders(
    orders: list[Order],
    hub: Hub,
    courier_abbreviation: str,
    courier_id: str,
    shipment_weight: float | None = None,
):
    results = {
        "success_orders": [
            # (order_id, response),
        ],
        "failed_orders": [
            # (order_id, error),
        ],
        "error": None,
    }

    courier = Courier.objects.get(abbreviation=courier_abbreviation)

    # ---- Warehouse ----
    warehouse_id = hub.json.get("fship_hub_id")

    if not warehouse_id:
        res = create_warehouse(hub).json()

        if not res.get("status"):
            results["error"] = (
                res.get("response", "Unknown error")
                .replace("at support@fship.in", "at support@idiotship.tech")
                .replace("fship", "")
            )
            return results

        warehouse_id = res["warehouseId"]
        hub.json["fship_hub_id"] = warehouse_id
        hub.save(update_fields=["json"])

    orders = orders.select_related(
        "shipping_address", "payment", "shipment"
    )
    orders = list(orders)

    successful_awbs = []
    success_orders = []

    # ======================================================
    # MAIN LOOP
    # ======================================================

    for order in orders:
        try:
            payload, err = build_payload(
                order, hub, warehouse_id, courier_id, shipment_weight=shipment_weight
            )
            if not payload:
                results["failed_orders"].append(
                    (
                        order.id,
                        f"Failed to build payload. Error: {err.get('error').replace('at support@fship.in', 'at support@idiotship.tech').replace('fship', '')}",
                    )
                )
                order.update_status("ready_to_ship")
                continue

            res_json = order_booking(payload).json()

            if not res_json.get("status"):
                results["failed_orders"].append(
                    (
                        order.id,
                        res_json.get("response", "Unkown error")
                        .replace("at support@fship.in", "at support@idiotship.tech")
                        .replace("fship", ""),
                    )
                )
                order.update_status("ready_to_ship")
                continue

            if "waybill" not in res_json:
                results["failed_orders"].append(
                    (
                        order.id,
                        res_json.get("response", "Unkown error")
                        .replace("at support@fship.in", "at support@idiotship.tech")
                        .replace("fship", ""),
                    )
                )
                order.update_status("ready_to_ship")
                continue

            awb = res_json["waybill"]

            order.json["order_creating_response"] = res_json
            order.awb_number = awb
            order.hub = hub
            order.logistic_partner = courier
            order.route_code = res_json.get("route_code", "")
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

            successful_awbs.append(awb)
            success_orders.append(order)
            results["success_orders"].append(
                (order.id, res_json),
            )

        except Exception as e:
            logger.exception("Bulk ship error")
            results["failed_orders"].append((order.id, str(e)))

    # ======================================================
    # BULK PICKUP REGISTER
    # ======================================================
    if successful_awbs:
        try:
            if "ats" in courier_abbreviation:
                for o in success_orders:
                    res_json = register_pickup([o.awb_number]).json()
                    o.json["register_pickup"] = res_json
                    o.save()
            else:
                register_pickup([o.awb_number for o in success_orders])
        except Exception as e:
            logger.exception("Error while registering pickup for bulk orders")

    return results
