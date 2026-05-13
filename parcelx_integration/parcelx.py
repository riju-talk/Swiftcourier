import base64
import json
import logging
from typing import List, Dict, Any, Optional

from django.conf import settings
from account import creds
import requests
from requests import Response

from account.models import Courier
from order_manager.models import Hub, Order, OrderItem


logger = logging.getLogger("my-logger")


def parcelx_get_access_token():
    """
    ParcelX does not use OAuth.
    Token = base64(ACCESS_KEY : SECRET_KEY)
    """
    raw = f"{settings.PARCELX_ACCESS_KEY}:{settings.PARCELX_SECRET_KEY}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def build_payload(order: Order, hub: Hub, mode="surface") -> Optional[Dict[str, Any]]:
    """
    Create payload for Xpressbees API.
    """
    pick_address_id = None
    try:
        res = create_warehouse(hub)
        res_json = res.json()

        if res_json.get("status") is True:
            pick_address_id = res_json["data"]["pick_address_id"]
            logger.info(
                f"Created warehouse in ParcelX, hub: {hub.id}, pick_address_id: {pick_address_id}"
            )
        else:
            try:
                r = list_warehouse()
                r_json = r.json()
                if r_json.get("status") is True:
                    warehouses = r_json.get("data", [])
                    for warehouse in warehouses:
                        if warehouse.get("title") == hub.name:
                            pick_address_id = warehouse.get("warehouse_id")
                            logger.info(
                                f"Found existing warehouse in ParcelX, hub: {hub.id}, pick_address_id: {pick_address_id}"
                            )
                            break
                else:
                    logger.error(
                        f"Failed to list warehouses in ParcelX, hub: {hub.id}, response: {r_json}"
                    )
                    return None
            except Exception as e:
                logger.exception(
                    f"Failed to list warehouses in ParcelX, hub: {hub.id}\nError: {e}"
                )
                return None

    except Exception as e:
        logger.exception(
            f"Failed to create warehouse in ParcelX, hub: {hub.id}\nError: {e}"
        )
        return None
    
    if pick_address_id is None:
        logger.error(f"pick_address_id is None for hub: {hub.id}")
        return None

    payload = {
        "client_order_id": str(order.get_order_id()),
        "consignee_emailid": order.shipping_address.email,
        "consignee_pincode": order.shipping_address.pin_code,
        "consignee_mobile": order.shipping_address.phone,
        "consignee_phone": order.shipping_address.phone,
        "consignee_address1": order.shipping_address.line1,
        "consignee_address2": order.shipping_address.line2 or "",
        "consignee_name": order.shipping_address.name,
        "invoice_number": "123456",
        "express_type": mode,
        "pick_address_id": pick_address_id,
        "return_address_id": "",
        "cod_amount": str(order.total_amount) if order.payment.method == "cod" else "0",
        "tax_amount": "0",
        "mps": "0",
        "courier_type": 0,  # 0 = priority, 1= courier selection (if you enter 1 then courier_code is required)
        "products": [
            {
                "product_name": item.product.name,
                "product_quantity": str(item.quantity),
                "product_value": str(int(item.unit_price)),
                "product_sku": item.sku_code,
            }
            for item in OrderItem.objects.filter(order=order)
        ],
        "address_type": "Home",
        "payment_mode": "Cod" if order.payment.method == "cod" else "Prepaid",
        "order_amount": order.total_amount,
        "extra_charges": "0",
        "shipment_width": [order.shipment.package_width_cm],
        "shipment_height": [order.shipment.package_height_cm],
        "shipment_length": [order.shipment.package_length_cm],
        "shipment_weight": [order.shipment.package_weight_kg],
    }
    return payload


# Base request function
def parcelx_request(
    request_method: str,
    payload: Optional[str],
    action_url: str,
    headers: Optional[dict] = None,
    base_url: str = "https://app.parcelx.in",
    api_url: str = "/api/v3",
    content_type: str = "application/json",
    is_api_key_required: bool = True,
    retry_count: int = 0,
    max_retries: int = 3,
) -> Response:
    url = f"{base_url}{api_url}{action_url}"
    headers = headers or {}
    headers.setdefault("Content-Type", content_type)

    if is_api_key_required:
        headers["access-token"] = parcelx_get_access_token()

    res = requests.request(
        method=request_method.upper(),
        url=url,
        headers=headers,
        data=payload if request_method.upper() != "GET" else None,
    )
    res_json = res.json()
    logger.info(f"parcelx Response: {res_json}")
    if (
        not res_json["status"]
        and res_json["responsemsg"] == "Invalid access-token"
        and retry_count < max_retries
    ):
        return parcelx_request(
            request_method,
            payload,
            action_url,
            headers,
            base_url,
            api_url,
            content_type,
            is_api_key_required,
            retry_count + 1,
            max_retries,
        )

    return res


# Shipment creation
def order_booking(shipment_data: Dict[str, Any]) -> Response:
    return parcelx_request(
        "POST",
        json.dumps(shipment_data),
        "/order/create_order",
    )


# Shipment tracking
def track_shipment(awb_number: str) -> Response:
    return parcelx_request(
        "GET",
        None,
        f"track_order?awb={awb_number}",
        headers={},
    )


# Generate manifest
# def generate_manifest(awb_list: List[str]) -> Response:
#     return xpressbees_request(
#         "POST",
#         json.dumps({"awbs": awb_list}),
#         "/shipments2/manifest",
#         headers={},
#     )


# Cancel shipment
def cancel_shipment(awb_number: str) -> Response:
    return parcelx_request(
        "POST",
        json.dumps({"awb": awb_number}),
        "/order/cancel_order",
        headers={},
    )


# Get courier list
def get_courier_list(token: str) -> Response:
    return parcelx_request(
        "POST", {"express_type": "surface"}, "/courier-list", headers={}
    )


# Serviceability check
# def check_serviceability(
#     token: str,
#     origin: str,
#     destination: str,
#     payment_type: str,
#     order_amount: str,
#     weight: Optional[str] = None,
#     length: Optional[str] = None,
#     breadth: Optional[str] = None,
#     height: Optional[str] = None,
# ) -> Response:
#     payload = {
#         "origin": origin,
#         "destination": destination,
#         "payment_type": payment_type,
#         "order_amount": order_amount,
#     }
#     optional_fields = {
#         "weight": weight,
#         "length": length,
#         "breadth": breadth,
#         "height": height,
#     }
#     payload.update({k: v for k, v in optional_fields.items() if v is not None})

#     return xpressbees_request(
#         "POST",
#         json.dumps(payload),
#         "/courier/serviceability",
#         headers={},
#     )


# NDR List
def get_ndr_list(
    ndr_type="initiated",
    from_date=None,
    to_date=None,
) -> Response:
    """ndr_type: ACTIVE or initiated
    from_date: 2022-04-01
    to_date: 2025-04-28"""
    query = []
    if ndr_type:
        query.append(f"ndr_type={ndr_type}")
    if from_date:
        query.append(f"from_date={from_date}")
    if to_date:
        query.append(f"to_date={to_date}")

    action = "/ndr-shipments"
    if query:
        action += "?" + "&".join(query)

    return parcelx_request("GET", None, action, headers={})


# NDR actions
def create_ndr_actions(actions: List[Dict[str, Any]]) -> Response:
    return parcelx_request(
        "POST",
        json.dumps(actions),
        "/ndr-action",
        headers={},
    )


def ship_order(order, hub):
    """
    Ship an order via Xpressbees API.

    :param order: Order instance
    :param hub: Hub instance
    :param payload: dict payload from build_payload()
    :return: (success: bool, response: dict)
    """
    try:
        payload = build_payload(order, hub)
        if payload is None:
            return False, {"error": "Failed to build payload for ParcelX"}
        # Make API request
        response = order_booking(payload)
        res_json = response.json()

        # ✅ Success
        if res_json.get("status") is True:
            data = res_json.get("data", {})

            order.json |= res_json
            order.awb_number = data.get("awb_number")
            order.update_status("pending_pickup")
            order.hub = hub
            order.logistic_partner = Courier.objects.get(abbreviation="px")
            order.save()

            return True, res_json

        # ❌ Failed
        else:
            message = res_json.get("responsemsg", "Unknown error")
            logger.error(f"ParcelX Order Failed: {message}\nresponse: {res_json}")
            return False, {"error": message, "response": res_json}

    except Exception as e:
        logger.exception("Xpressbees Ship Order Exception")
        return False, {"error": str(e)}


def create_warehouse(hub: Hub):
    return parcelx_request(
        request_method="POST",
        payload=json.dumps(
            {
                "address_title": hub.name,
                "sender_name": hub.contact_person,
                "full_address": f"{hub.address_line1} {hub.address_line2 or ''}, {hub.city}, {hub.state}",
                "phone": hub.phone,
                "pincode": hub.pin_code,
            }
        ),
        action_url="/create_warehouse",
    )


def remove_warehouse(warehouse_id: int):
    return parcelx_request(
        request_method="POST",
        payload=json.dumps({"warehouse_id": str(warehouse_id)}),
        action_url="/remove-warehouse",
    )


def list_warehouse():
    return parcelx_request(
        request_method="GET",
        action_url="/warehouse-list",
        payload={}
    )
