from collections.abc import Callable
import json
import logging
from typing import Dict, Any, Optional

import requests
from requests import Response

# from django.utils import timezone
from datetime import timezone

from account import creds
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from account.models import Courier
from order_manager.models import Hub, Order, OrderItem


logger = logging.getLogger("my-logger")
base_url = "https://api.boxdlogistics.com/seller/v1/"


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
def bdlogistic_request(
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

    if is_token_required and creds.BDL_TOKEN:
        headers.setdefault("Authorization", f"Token {creds.BDL_TOKEN.strip()}")

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
            logger.warning("BDL: token expired or unauthorized. Retrying once...")

            # 👉 If you have token refresh logic, call it here
            # refresh_bdl_token()

            headers["Authorization"] = f"Token {creds.BDL_TOKEN.strip()}"

            res = SESSION.request(
                method=method.upper(),
                url=url,
                headers=headers,
                data=data,
                timeout=(5, 20),
            )

        return res

    except requests.exceptions.RequestException as e:
        logger.warning("BDL: Session possibly dead. Recreating session...")

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
            logger.exception("BDL: request failed after session reset -> %s", url)
            raise


# ==========================================================
# PAYLOAD BUILDER
# ==========================================================
def build_payload(
    order: Order,
    hub: Hub,
    warehouse_id: int,
    courier_id: int,
    bdl_request: Callable = bdlogistic_request,
    mode="surface",
) -> Optional[Dict[str, Any]]:
    items = []
    for item in OrderItem.objects.filter(order=order):
        items.append(
            {
                "sku": item.sku_code,
                "name": item.product.name,
                "description": item.product.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                # "category": None,
                # "discount_amount": 20,
                # "is_tax_inclusive": False,
                # "tax_rate": "18.00",
                # "cgst_tax_rate": None,
                # "sgst_tax_rate": None,
                # "igst_tax_rate": None,
                # "cess_tax_rate": None,
                # "hsn_code": "3231",
                # "length_in_cm": "10.00",
                # "breadth_in_cm": "20.00",
                # "height_in_cm": "34.00",
                # "weight_in_gm": "0.40",
                # "vol_weight_in_gm": "1360.00",
            }
        )

    payload = {
        "order_number": str(order.order_number),
        "order_invoice_number": None,
        "customer_name": order.shipping_address.name,
        "customer_email": order.shipping_address.email,
        "customer_phone_number": order.shipping_address.phone,
        "customer_isd_code": "+91",
        "customer_gst_number": None,
        "warehouse_id": warehouse_id,
        "shipping_name": order.shipping_address.name,
        "shipping_email": order.shipping_address.email,
        "shipping_phone_number": order.shipping_address.phone,
        "shipping_isd_code": "+91",
        "shipping_alt_phone_number": order.shipping_address.alt_phone,
        "shipping_alt_isd_code": "+91",
        "shipping_address_type": order.shipping_address.label,
        "shipping_address_line1": order.shipping_address.line1,
        "shipping_address_line2": order.shipping_address.line2,
        "shipping_landmark": order.shipping_address.landmark,
        "shipping_pincode": order.shipping_address.pin_code,
        "shipping_city": order.shipping_address.city,
        "shipping_state": order.shipping_address.state,
        "shipping_country": order.shipping_address.country,
        "shipping_latitude": None,
        "shipping_longitude": None,
        # "billing_name": "princekthakur",
        # "billing_email": "prince@gmail.com",
        # "billing_phone_number": 8569065690,
        # "billing_isd_code": "+91",
        # "billing_alt_phone_number": None,
        # "billing_alt_isd_code": "+91",
        # "billing_address_type": "office",
        # "billing_address_line1": "west patel nagar new deelhi",
        # "billing_address_line2": None,
        # "billing_landmark": "RBI tower",
        # "billing_pincode": "110008",
        # "billing_city": "new delhi",
        # "billing_state": "new delhi",
        # "billing_country": "India",
        # "billing_latitude": None,
        # "billing_longitude": None,
        "package_length_in_cm": str(order.shipment.package_length_cm),
        "package_breadth_in_cm": str(order.shipment.package_width_cm),
        "package_height_in_cm": str(order.shipment.package_height_cm),
        "package_weight_in_gm": str(order.shipment.package_weight_kg * 1000),
        "cgst_amount": None,
        "sgst_amount": None,
        "igst_amount": None,
        "cess_amount": None,
        "cgst_tax_rate": None,
        "sgst_tax_rate": None,
        "igst_tax_rate": None,
        "cess_tax_rate": None,
        "is_tax_inclusive": False,
        "tax_rate": None,
        "tax_amount": None,
        "shipping_charges": None,
        "discount_amount": order.payment.discount,
        "subtotal_amount": order.total_amount,
        "total_amount": str(order.total_amount),
        "payment_mode": order.payment.method,
        "tags": None,
        "notes": None,
        "is_cod": order.payment.method == "cod",
        "cod_collectable_amount": (
            str(order.payment.method) if order.payment.method == "cod" else 0
        ),
        "is_mps": False,
        "is_reverse": False,
        # "order_date": "2025-08-21T09:50:25.972484Z",
        "order_date": order.created_at.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "products": items,
    }
    return payload, None


# ==========================================================
# PICKUP LOCATION (WAREHOUSE)
# ==========================================================


def list_warehouse(
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
) -> Response:
    raise NotImplementedError()


def create_warehouse(
    hub: Hub,
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
) -> Response:
    payload = {
        "full_name": hub.contact_person,
        "warehouse_name": hub.name,
        "address_line1": hub.address_line1,
        "state": hub.state,
        "city": hub.city,
        "landmark": "",
        "pincode": hub.pin_code,
        "country": hub.country,
        "support_phone_number": hub.phone,
        "phone_number": hub.phone,
        "return_full_name": None,
        "return_warehouse_name": None,
        "return_email": None,
        "return_phone_number": None,
        "return_isd_code": "+91",
        "return_alt_phone_number": None,
        "return_alt_isd_code": "+91",
        "return_support_phone_number": None,
        "return_support_isd_code": "+91",
        "return_address_line1": None,
        "return_address_line2": None,
        "return_landmark": None,
        "return_pincode": None,
        "return_city": None,
        "return_state": None,
        "return_country": None,
        "return_latitude": None,
        "return_longitude": None,
        "return_gst_number": None,
        "same_as_rto_address": True,
    }
    return bdl_request(
        "POST",
        json.dumps(payload),
        "/warehouse/create/",
    )


def remove_warehouse(
    warehouse_id: int,
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
) -> Response:
    raise NotImplementedError()


# ==========================================================
# SHIPMENT
# ==========================================================
def order_booking(
    shipment_data: Dict[str, Any],
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
) -> Response:
    return bdl_request(
        "POST",
        json.dumps(shipment_data),
        "/order/create/",
    )


def assign_awb(
    shipment_ids: list[int],
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
    courier_id: Optional[int] = None,
) -> Response:
    payload = {"order_ids": shipment_ids}

    if courier_id is not None:
        payload["courier_id"] = courier_id

    return bdl_request(
        "POST",
        json.dumps(payload),
        "/order/bulk-ship/",
    )


def track_shipment(
    awb_number: str,
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
) -> Response:
    payload = {"waybill": str(awb_number)}
    return bdl_request(
        "POST",
        payload,
        "/trackinghistory",
    )


def cancel_shipment(
    awb_number: str,
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
) -> Response:
    return bdl_request(
        "POST",
        json.dumps({"waybill": str(awb_number)}),
        "/cancelorder",
    )


def get_courier_list(
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
    token: str = "",
) -> Response:
    return bdl_request("GET", None, "/getallcourier")


# ==========================================================
# NDR
# ==========================================================


def get_ndr_list(
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
    ndr_type="initiated",
    from_date=None,
    to_date=None,
) -> Response:
    return bdl_request("GET", None, "/ndr/all")


def create_ndr_actions(
    awb_no: str,
    bdl_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ] = bdlogistic_request,
) -> Response:
    return bdl_request(
        "POST",
        json.dumps(
            {"action": "return", "comments": "The Buyer does not want the product"}
        ),
        f"/ndr/{awb_no}/action",
    )


def register_pickup(
    awbs: list[str], bdl_request: Callable = bdlogistic_request
) -> Response:
    return bdl_request("POST", json.dumps({"waybills": awbs}), "/registerpickup")


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

    res_json = bdlogistic_request(
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
    bdl_request: Callable = bdlogistic_request,
):
    try:
        warehouse_id = hub.json.get("bdl_hub_id")
        if not warehouse_id:
            res_json = create_warehouse(hub, bdl_request).json()
            if res_json.get("detail"):
                return False, {
                    "error": res_json.get("detail", "Unknown error")
                    .replace("at support@boxdlogistics.in", "at support@idiotship.tech")
                    .replace("boxdlogistics", "")
                }
            else:
                warehouse_id = res_json.get("id")
                hub.json["bdl_hub_id"] = warehouse_id
                hub.save()

        payload, error = build_payload(
            order, hub, warehouse_id, courier_id, bdlogistic_request
        )
        if not payload:
            return False, {
                "error": f"Failed to build payload. Error: {error.get('error')}"
            }

        logger.debug(f"BDL: Order Payload: {payload}")

        res_json = order_booking(payload, bdl_request).json()
        bdl_order_id = res_json.get("id")
        if not bdl_order_id or "awb_number" not in res_json:
            return False, {
                "error": res_json.get("response", "Unknown error")
                .replace("at support@bdl.in", "at support@idiotship.tech")
                .replace("bdl", "")
            }

        try:
            if res_json.get("errors"):
                for k, v in res_json.get("errors").items():
                    return False, {"errors": f"{k}: {','.join(v)}"}
        except:
            pass

        logger.debug(f"BDL: Order Booking Response: {res_json}")

        order.json |= {"order_creating_response": res_json}

        res_json1 = assign_awb([bdl_order_id], bdl_request, courier_id).json()
        logger.debug(f"BDL: Assign AWB Response: {res_json1}")

        if err := res_json1.get(str(bdl_order_id), {}).get("detail"):
            logger.warning(f"BDL: Assign AWB Error: {err}")
            return False, {"error": err.replace("bdl", "idiotship")}

        logger.debug(f"Assigning AWB Response: {res_json1}")

        order.json["register_pickup"] = res_json1

        order.awb_number = res_json1.get(bdl_order_id).get("awb_number")
        order.route_code = res_json1.get(bdl_order_id).get("route_code")
        order.hub = hub
        order.logistic_partner = Courier.objects.get(abbreviation=courier_abbreviation)
        order.update_status("pending_pickup")
        order.save()

        return True, order.awb_number

    except Exception as e:
        logger.exception("BDL: Ship Order Exception")
        return False, {"error": str(e)}


def bulk_ship_orders(
    orders: list[Order],
    hub: Hub,
    courier_abbreviation: str,
    courier_id: str,
):

    results = {
        "success_orders": [
            # ("order_id", response),
        ],
        "failed_orders": [
            # ("order_id", response),
        ],
        "error": None,
    }

    # ---- Cache courier ----
    courier = Courier.objects.get(abbreviation=courier_abbreviation)

    # ---- Warehouse ----
    warehouse_id = hub.json.get("bdl_hub_id")

    if not warehouse_id:
        res = create_warehouse(hub).json()

        if not res.get("id"):
            results["error"]= res.get("detail", "Unknown error").replace("at support@bdl.in", "at support@idiotship.tech").replace("bdl", "")
            return results

        warehouse_id = res["id"]
        hub.json["bdl_hub_id"] = warehouse_id
        hub.save(update_fields=["json"])

    # ---- Prefetch related objects ----
    orders = orders.select_related(
        "shipping_address", "payment", "shipment"
    ).prefetch_related("orderitem_set__product")

    # successful_shipment_ids = []
    success_orders = []

    # ======================================================
    # MAIN LOOP
    # ======================================================

    for order in orders:
        try:
            payload, err = build_payload(order, hub, warehouse_id, courier_id)
            if not payload:
                results["failed_orders"].append(
                    (
                        order.id,
                        f"Failed to build payload. Error: {err.get('error').replace('at support@bdl.in', 'at support@idiotship.tech').replace('bdl', '')}",
                    )
                )
                continue

            res_json = order_booking(payload).json()
            shipment_id = res_json.get("id")

            if not shipment_id:
                results["failed_orders"].append(
                    (
                        order.id,
                        res_json.get("deatil", "Unkown error")
                        .replace("at support@bdl.in", "at support@idiotship.tech")
                        .replace("bdl", ""),
                    )
                )
                continue

            if "awb_number" not in res_json:
                results["failed_orders"].append(
                    (
                        order.id,
                        res_json.get("detail", "Unkown error")
                        .replace("at support@bdl.in", "at support@idiotship.tech")
                        .replace("bdl", ""),
                    )
                )
                continue

            order.json["order_creating_response"] = res_json
            # order.hub = hub
            # order.logistic_partner = courier
            # order.update_status("pending_pickup")

            order.save(
                update_fields=[
                    "json",
                    # "awb_number",
                    # "hub",
                    # "logistic_partner",
                    # "status",
                ]
            )

            # successful_shipment_ids.append(shipment_id)
            success_orders.append((order, shipment_id))
            results["success_orders"].append(
                (order.id, res_json)
            )

        except Exception as e:
            logger.exception("BDL: Bulk ship error")
            results["failed_orders"].append((order.id, str(e)))

    # ======================================================
    # BULK PICKUP REGISTER
    # ======================================================
    res_json = assign_awb([i for _, i in success_orders], courier_id=courier_id).json()
    if res_json.get("detail"):
        pass

    for order, shipment_id in success_orders:
        data = res_json.get(shipment_id)
        if data:
            order.hub = hub
            order.logistic_partner = courier
            order.awb_number = data.get("awb_number")
            order.update_status("pending_pickup")
            order.save(
                update_fields=[
                    "hub",
                    "logistic_partner",
                    "awb_number",
                ]
            )
        else:
            results["failed_orders"].append((order.id, "Failed to ship order"))

    # if successful_awbs:
    #     try:
    #         if "ats" in courier_abbreviation:
    #             for o in success_orders:
    #                 res_json = register_pickup([o.awb_number]).json()
    #                 o.json["register_pickup"] = res_json
    #                 o.save()
    #         else:
    #             register_pickup([o.awb_number for o in success_orders])
    #     except Exception as e:
    #         logger.exception("BDL: Error while registering pickup for bulk orders")

    return results
