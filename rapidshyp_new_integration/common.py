from collections.abc import Callable
import json
import logging
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
base_url = "https://api.rapidshyp.com/rapidshyp/apis/v1"


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
def rapidshyp_request(
    method: str,
    payload: Optional[Any],
    action_url: str,
    headers: Optional[dict] = None,
    is_token_required: bool = True,
) -> requests.Response:

    global SESSION

    url = f"{base_url.rstrip('/')}{action_url}"
    headers = headers.copy() if headers else {}

    headers.setdefault("Content-Type", "application/json")
    if is_token_required and creds.RAPIDSHYP_NEW_TOKEN:
        headers.setdefault("rapidshyp-token", creds.RAPIDSHYP_NEW_TOKEN.strip())

    data = payload if isinstance(payload, str) else json.dumps(payload)

    try:
        res = SESSION.request(
            method=method.upper(),
            url=url,
            headers=headers,
            data=data,
            timeout=(5, 20),
        )

        # ⭐ Handle token expiry automatically
        if res.status_code in [401, 403]:
            logger.warning("RapidShyp token expired or unauthorized. Retrying once...")

            # 👉 If you have token refresh logic, call it here
            # refresh_rapidshyp_token()

            headers["rapidshyp-token"] = creds.RAPIDSHYP_NEW_TOKEN.strip()

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
            logger.exception("RapidShyp request failed after session reset -> %s", url)
            raise


# ==========================================================
# PAYLOAD BUILDER
# ==========================================================
def build_payload(
    order: Order,
    hub: Hub,
    warehouse_name: str,
    courier_id: int,
    rs_request: Callable = rapidshyp_request,
    mode="surface",
    shipment_weight: float | None = None,
) -> Optional[Dict[str, Any]]:
    items = []
    for item in OrderItem.objects.filter(order=order):
        items.append(
            {
                "itemName": item.product.name[:90],
                "sku": "",
                "description": item.product.description or "No description",
                "units": item.quantity,
                "unitPrice": item.unit_price,
                "tax": 0,
                # "hsn": "HSN123",
                # "productLength": 10,
                # "productBreadth": 5,
                # "productHeight": 2,
                # "productWeight": 0.5,
                # "brand": "Brand A",
                # "imageURL": "https://abcd.jpeg",
                # "isFragile": False,
                # "isPersonalisable": False,
                # "pickupAddressName": "",
            }
        )

    payload = {
        "orderId": f"{order.get_order_id_for_aggregator()}-{random.randint(100000, 999999)}",
        "orderDate": order.created_at.strftime("%Y-%m-%d"),  # 2026-03-02
        "pickupAddressName": warehouse_name,
        # "pickupLocation": {
        #     "contactName": hub.contact_person,
        #     "pickupName": hub.name,
        #     "pickupEmail": hub.email,
        #     "pickupPhone": hub.phone,
        #     "pickupAddress1": hub.address_line1,
        #     "pickupAddress2": hub.address_line2,
        #     "pinCode": hub.pin_code,
        # },
        # "rto_Location": {
        #     "rto_locationName": "RAPIDwsQAA",
        #     "contactName": "RAPIDQasA",
        #     "rtoEmail": "abc@gmail.com",
        #     "rtoPhone": "9999999999",
        #     "rtoAddress1": "aRAPIDQA",
        #     "rtoAddress2": "",
        #     "rtopinCode": "201301",
        # },
        "storeName": "DEFAULT",
        "billingIsShipping": True,
        "shippingAddress": {
            "firstName": order.shipping_address.name,
            "lastName": "N/A",
            "addressLine1": (
                order.shipping_address.line1[:99]
                if order.shipping_address.line1
                else ""
            ),
            "addressLine2": (
                order.shipping_address.line2[:99]
                if order.shipping_address.line2
                else ""
            ),
            "pinCode": order.shipping_address.pin_code,
            "email": order.shipping_address.email or "support@idiotship.tech",
            "phone": order.shipping_address.phone,
        },
        # "billingAddress": {
        #     "firstName": "Jane",
        #     "lastName": "Doegghgh",
        #     "addressLine1": "456 Elm St",
        #     "addressLine2": "Apt 101",
        #     "pinCode": "110002",
        #     "email": "jane.doe@example.com",
        #     "phone": "9999999999",
        # },
        "orderItems": items,
        "paymentMethod": "COD" if order.payment.method == "cod" else "PREPAID",
        # "shippingCharges": 100,
        # "giftWrapCharges": 10,
        # "transactionCharges": 20,
        # "totalDiscount": 5,
        # "codCharges": 20,
        # WORK IN PARTIAL PAID SYSTEM
        # "prepaidAmount": 50,
        "packageDetails": {
            "packageLength": order.shipment.package_length_cm,
            "packageBreadth": order.shipment.package_width_cm,
            "packageHeight": order.shipment.package_height_cm,
            "packageWeight": (
                order.shipment.package_weight_kg * 1000
                if shipment_weight is None
                else shipment_weight
            ),
        },
    }

    return payload, None


# ==========================================================
# PICKUP LOCATION (WAREHOUSE)
# ==========================================================
def list_warehouse(
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
) -> Response:
    raise NotImplementedError()


def create_warehouse(
    hub: Hub,
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
) -> Response:
    payload = {
        "address_name": hub.name,
        "contact_name": hub.contact_person,
        "contact_number": hub.phone,
        "email": hub.email,
        "address_line": hub.address_line1,
        "address_line2": hub.address_line2,
        "pincode": hub.pin_code,
        "gstin": "",
        "dropship_location": True,
        "use_alt_rto_address": False,
        # "rto_address": "",
        # "create_rto_address": {
        #     "rto_address_name": "Warehouse2",
        #     "rto_contact_name": "Sergio Ramos",
        #     "rto_contact_number": "9999999999",
        #     "rto_email": "jane.smith@example.com",
        #     "rto_address_line": "456 RTO Rd",
        #     "rto_address_line2": "Building B",
        #     "rto_pincode": "110001",
        #     "rto_gstin": "",
        # },
    }
    return rs_request(
        "POST",
        json.dumps(payload),
        "/create/pickup_location",
    )


def remove_warehouse(
    warehouse_id: int,
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
) -> Response:
    raise NotImplementedError()


# ==========================================================
# SHIPMENT
# ==========================================================
def order_booking(
    shipment_data: Dict[str, Any],
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
) -> Response:
    return rs_request(
        "POST",
        json.dumps(shipment_data),
        "/create_order",
    )


def assign_awb(
    shipment_id: int,
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
    courier_id: Optional[int] = None,
) -> Response:
    payload = {"shipment_id": shipment_id}

    if courier_id is not None:
        payload["courier_code"] = courier_id

    return rs_request(
        "POST",
        json.dumps(payload),
        "/assign_awb",
    )


def track_shipment(
    awb_number: str,
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
) -> Response:
    payload = {"waybill": str(awb_number)}
    return rs_request(
        "POST",
        payload,
        "/trackinghistory",
    )


def cancel_shipment(
    awb_number: str | None = None,
    order: Order | None = None,
    rs_request: Callable = rapidshyp_request,
) -> Response:
    if order is None:
        order = Order.objects.filter(awb_number=awb_number).first()

    if order:
        order_id = order.json.get("order_creating_response", {}).get("order_id", "")
    else:
        order_id = ""

    return rs_request(
        "POST",
        json.dumps({"orderId": str(order_id), "storeName": "DEFAULT"}),
        "/cancel_order",
    )


def cancel_bulk_orders(orders: list[Order], hub = None):
    """Bulk cancel orders"""
    for o in orders:
        try:
            cancel_shipment(order=o)
        except:
            pass


def get_courier_list(
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
    token: str = "",
) -> Response:
    return rs_request("GET", None, "/getallcourier")


def approve_order(
    order_ids: list[str],
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
) -> Response:
    return rs_request(
        "POST",
        json.dumps({"order_id": order_ids}),
        "/approve_orders",
    )


# ==========================================================
# NDR
# ==========================================================
def get_ndr_list(
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
    ndr_type="initiated",
    from_date=None,
    to_date=None,
) -> Response:
    return rs_request("GET", None, "/ndr/all")


def create_ndr_actions(
    awb_no: str,
    rs_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = rapidshyp_request,
) -> Response:
    return rs_request(
        "POST",
        json.dumps(
            {"action": "return", "comments": "The Buyer does not want the product"}
        ),
        f"/ndr/{awb_no}/action",
    )


def register_pickup(
    awbs: str, shipment_id: str, rs_request: Callable = rapidshyp_request
) -> Response:
    return rs_request(
        "POST",
        json.dumps({"awb": awbs, "shipment_id": shipment_id}),
        "/schedule_pickup",
    )


# ==========================================================
# HIGH LEVEL ORCHESTRATION
# ==========================================================
def generate_label(
    orders: list[Order],
) -> tuple[Exception | bool, list[str] | None]:
    shipmentIds = []
    for i in orders:
        try:
            if shipmentId := i.json.get("assign_awb_response", {}).get(
                "shipment_id", ""
            ):
                if shipmentId:
                    shipmentIds.append(str(shipmentId))
        except:
            continue

    payload = {"shipmentId": shipmentIds}

    res_json = rapidshyp_request("POST", json.dumps(payload), "/generate_label").json()
    ats_url = res_json.get("label_url")
    if ats_url:
        return False, ats_url
    else:
        logger.error(f"Failed to fetch ats label: {res_json}")

    return True, ValueError("Urls doesn't exists")


def ship_order(
    order: Order,
    hub: Hub,
    courier_abbreviation: str,
    courier_id: str,
    return_shipment: bool = False,
    shipment_weight: float | None = None,
    rs_request: Callable = rapidshyp_request,
):
    try:
        warehouse_name = hub.json.get("rapidshyp_new_hub_name")
        if not warehouse_name:
            res_json = create_warehouse(hub, rs_request).json()
            status = res_json.get("status")
            if not status or status.lower() != "success":
                err = (
                    res_json.get("remarks") or res_json.get("remark") or "Unknown error"
                )
                return False, {
                    "error": err.replace(
                        "at support@rapidshyp.in", "at support@idiotship.tech"
                    ).replace("rapidshyp", "")
                }
            else:
                warehouse_name = res_json.get("pickup_location_name")
                hub.json["rapidshyp_new_hub_name"] = warehouse_name
                hub.save()

        payload, error = build_payload(
            order=order,
            hub=hub,
            warehouse_name=warehouse_name,
            courier_id=courier_id,
            rs_request=rs_request,
            shipment_weight=shipment_weight,
        )
        if not payload:
            return False, {
                "error": f"Failed to build payload. Error: {error.get('error', 'Unknown error').replace('at support@rapidshyp.in', 'at support@idiotship.tech').replace('rapidshyp', '')}"
            }

        res_json1 = order_booking(payload, rs_request).json()
        status1 = res_json1.get("status")
        if not status1 or status1.lower() != "success":
            err = res_json1.get("remarks") or res_json1.get("remark") or "Unknown error"
            return False, {
                "error": err.replace(
                    "at support@rapidshyp.in", "at support@idiotship.tech"
                ).replace("rapidshyp", "")
            }

        try:
            if res_json1.get("remarks"):
                for k, v in res_json1.get("remarks").items():
                    return False, {"errors": f"{k}: {','.join(v)}"}
        except:
            pass

        order.json |= {"order_creating_response": res_json1}

        shipment_id = res_json1.get("shipment", [{}])[0].get("shipment_id", "")
        order_id = res_json1.get("order_id", "")

        res_json2 = approve_order([order_id], rs_request).json()
        order.json["approve_order_response"] = res_json2

        res_json3 = assign_awb(
            shipment_id=shipment_id, courier_id=courier_id, rs_request=rs_request
        ).json()
        status3 = res_json3.get("status")
        if not status3 or status3.lower() != "success":
            err = res_json3.get("remarks") or res_json3.get("remark") or "Unknown error"
            return False, {
                "error": err.replace(
                    "at support@rapidshyp.in", "at support@idiotship.tech"
                ).replace("rapidshyp", "")
            }

        order.json["assign_awb_response"] = res_json3
        awb_no = res_json3.get("awb")

        res_json4 = register_pickup(
            awb_no, shipment_id=shipment_id, rs_request=rs_request
        ).json()
        status4 = res_json4.get("status")
        if not status4 or status4.lower() != "success":
            err = res_json4.get("remarks") or res_json4.get("remark") or "Unknown error"
            return False, {
                "error": err.replace(
                    "at support@rapidshyp.in", "at support@idiotship.tech"
                ).replace("rapidshyp", "")
            }

        order.json["register_pickup"] = res_json4

        order.awb_number = awb_no
        order.route_code = res_json4.get("routingCode", "")
        order.hub = hub
        order.logistic_partner = Courier.objects.get(abbreviation=courier_abbreviation)
        order.update_status("pending_pickup")
        order.save()

        return True, order.awb_number

    except Exception as e:
        logger.exception("RapidShyp Ship Order Exception")
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

    # ---- Cache courier ----
    courier = Courier.objects.get(abbreviation=courier_abbreviation)

    # ---- Warehouse ----
    warehouse_name = hub.json.get("rapidshyp_new_hub_name")

    if not warehouse_name:
        res = create_warehouse(hub).json()
        status = res.get("status")
        if not status or status.lower() != "success":
            err = res.get("remarks") or res.get("remark") or "Unknown error"
            err = err.replace(
                "at support@rapidshyp.in", "at support@idiotship.tech"
            ).replace("rapidshyp", "")
            results["error"] = f"Error while creating hub: {err}"
            return results

        warehouse_name = res["pickup_location_name"]
        hub.json["rapidshyp_new_hub_name"] = warehouse_name
        hub.save(update_fields=["json"])

    # ---- Prefetch related objects ----
    orders = orders.select_related("shipping_address", "payment", "shipment")

    success_orders = []

    # ======================================================
    # MAIN LOOP
    # ======================================================
    for order in orders:
        try:
            payload, error = build_payload(
                order=order,
                hub=hub,
                warehouse_name=warehouse_name,
                courier_id=courier_id,
                rs_request=rapidshyp_request,
                shipment_weight=shipment_weight,
            )
            if not payload:
                results["failed_orders"].append(
                    (
                        order.id,
                        error.get("error", "Unknown error")
                        .replace("at support@rapidshyp.in", "at support@idiotship.tech")
                        .replace("rapidshyp", ""),
                    )
                )
                order.update_status("ready_to_ship")
                continue

            res_json1 = order_booking(payload, rapidshyp_request).json()
            status1 = res_json1.get("status")

            if not status1 or status1.lower() != "success":
                err = (
                    res_json1.get("remarks")
                    or res_json1.get("remark")
                    or "Unknown error"
                )
                results["failed_orders"].append(
                    (
                        order.id,
                        err,
                    )
                )
                order.update_status("ready_to_ship")
                continue

            try:
                if res_json1.get("remarks"):
                    for k, v in res_json1.get("remarks").items():
                        results["failed_orders"].append(
                            (
                                order.id,
                                f"Failed to build payload. Error: {k}: {','.join(v)}",
                            )
                        )
                        order.update_status("ready_to_ship")
                        continue
            except:
                pass

            shipment_id = res_json1.get("shipment", [{}])[0].get("shipment_id", "")
            order.json |= {"order_creating_response": res_json1}
            order_id = res_json1.get("order_id", "")

            # res_json2 = approve_order([order_id], rapidshyp_request).json()
            # order.json["approve_order_response"] = res_json2

            # if not res_json2.get('success_count', 0):
            #     err = (
            #         res_json2.get("remarks")
            #         or res_json2.get("remark")
            #         or "Unknown error"
            #     )
            #     results["failed_orders"].append(
            #         (
            #             order.id,
            #             err.replace(
            #                 "at support@rapidshyp.in", "at support@idiotship.tech"
            #             ).replace("rapidshyp", ""),
            #         )
            #     )
            #     order.update_status("ready_to_ship")
            #     order.save()
            #     continue

            res_json3 = assign_awb(
                shipment_id=shipment_id,
                courier_id=courier_id,
                rs_request=rapidshyp_request,
            ).json()
            status3 = res_json3.get("status")
            if not status3 or status3.lower() != "success":
                err = (
                    res_json3.get("remarks")
                    or res_json3.get("remark")
                    or "Unknown error"
                )
                results["failed_orders"].append(
                    (
                        order.id,
                        err.replace(
                            "at support@rapidshyp.in", "at support@idiotship.tech"
                        ).replace("rapidshyp", ""),
                    )
                )
                order.update_status("ready_to_ship")
                continue

            order.json["assign_awb_response"] = res_json3
            awb_no = res_json3.get("awb")

            res_json4 = register_pickup(
                awb_no, shipment_id=shipment_id, rs_request=rapidshyp_request
            ).json()
            status4 = res_json4.get("status")
            if not status4 or status4.lower() != "success":
                err = (
                    res_json4.get("remarks")
                    or res_json4.get("remark")
                    or "Unknown error"
                )
                results["failed_orders"].append(
                    (
                        order.id,
                        err.replace(
                            "at support@rapidshyp.in", "at support@idiotship.tech"
                        ).replace("rapidshyp", ""),
                    )
                )
                order.update_status("ready_to_ship")
                continue

            order.json["register_pickup"] = res_json4

            order.awb_number = awb_no
            order.route_code = res_json4.get("routingCode", "")
            order.hub = hub
            order.logistic_partner = Courier.objects.get(
                abbreviation=courier_abbreviation
            )
            order.update_status("pending_pickup")
            order.save()

            results["success_orders"].append((order.id, res_json1))

        except Exception as e:
            logger.exception("Bulk ship error")
            order.update_status("ready_to_ship")
            results["failed_orders"].append((order.id, str(e)))

    # ======================================================
    # BULK PICKUP REGISTER
    # ======================================================

    return results
