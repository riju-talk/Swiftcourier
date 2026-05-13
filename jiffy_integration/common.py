import logging
import requests

from collections.abc import Callable
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from utils.clean import clean_aggregator_or_courier_name
from django.utils import timezone

from account import creds
from account.models import Courier
from order_manager.models import Order, OrderItem


logger = logging.getLogger("my-logger")


# Helper: build payload for Jiffy 'allocate_waybill' API
def build_payload(order, hub, return_shipment: bool = False) -> Dict[str, Any]:
    """
    Based on the API spec in the uploaded PDF. Mandatory fields included.
    See the uploaded doc for full spec. :contentReference[oaicite:1]{index=1}
    """
    # items
    items = []
    for item in OrderItem.objects.filter(order=order):
        items.append(
            {
                "title": item.product.name,
                "qty": int(item.quantity),
                "sku": item.sku_code or "",
                "price": float(item.unit_price),
            }
        )

    payment_mode = (
        "cod" if getattr(order.payment, "method", "").lower() == "cod" else "prepaid"
    )

    payload = {
        "order_number": str(order.get_order_id()),
        "collectable_amount": float(order.total_amount),
        "payment_method": payment_mode.lower(),
        "shipping_address": {
            "company": order.shipping_address.company_name or "N/A",
            "first_name": order.shipping_address.name,
            "last_name": "N/A",
            "address": order.shipping_address.line1,
            "address_2": order.shipping_address.line2 or "",
            "phone_no": order.shipping_address.phone,
            "city": order.shipping_address.city,
            "state": order.shipping_address.state,
            "country": getattr(order.shipping_address, "country", "India"),
            "pincode": str(order.shipping_address.pin_code),
        },
        # "billing_address": {
        #     "company": "compnay name here",
        #     "first_name": "John",
        #     "last_name": "Doe",
        #     "address": "123 Main Street, Apartment 4B",
        #     "address_2": "Near Central Park",
        #     "phone_no": "9876543210",
        #     "city": "Mumbai",
        #     "state": "Maharashtra",
        #     "country": "India",
        #     "pincode": "400001",
        #     "gst_number": "27ABCDE1234F1Z5",
        # },
        "products": items,
        "weight": order.shipment.package_weight_kg,
        "package_length": order.shipment.package_length_cm,
        "package_breadth": order.shipment.package_width_cm,
        "package_height": order.shipment.package_height_cm,
        "shipping_charges": order.payment.shipping_charges or 0,
        "cod_charges": order.payment.cod_charges or 0,
        "tax_amount": order.payment.tax_percent or 0,
        "total_amount": float(order.total_amount),
        "discount": order.payment.discount or 0,
        "tags": ["N/A"],
        "order_date": (
            order.created_at.timestamp()
            if hasattr(order, "created_at")
            else timezone.now().timestamp()
        ),
        "checkout_id": "N/A",
    }

    return payload


# Waybill generation (order booking)
def order_booking(
    shipment_data: Dict[str, Any],
    jf_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:
    return jf_request(
        "POST",
        shipment_data,
        "/orders",
        headers={},
    )


# Cancel order (POST /cancel)
def cancel_shipment(
    shipment_id: str,
    jf_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:

    o = Order.objects.filter(awb_number=shipment_id).first()
    if not o:
        raise ValueError(f"Order with AWB {shipment_id} not found.")
    try:
        shipment_id = (
            o.json.get("awb_generation", {})
            .get("data", {})
            .get("results", [])[0]
            .get("shipment_id")
        )
        if not shipment_id:
            raise ValueError(f"Shipment ID not found for order with AWB {shipment_id}.")

        return jf_request(
            "POST", {"shipment_ids": [shipment_id]}, "/shipments/cancel", headers={}
        )
    except Exception as e:
        logger.exception("Failed to get shipment ID from order JSON")
        raise ValueError(f"Shipment ID not found for order with AWB {shipment_id}.")


def cancel_bulk_orders(orders: list[Order], jf_request: Callable):
    '''Bulk cancel orders
    '''
    shipment_ids = []
    for o in orders:
        try:
            s_id = str(
                o.json.get("awb_generation", {})
                .get("data", {})
                .get("results", [])[0]
                .get("shipment_id")
            )
            if s_id:
                shipment_ids.append(s_id)
        except:
            pass

    return jf_request(
        "POST", {"order_ids": [shipment_ids]}, "/orders/cancel", headers={}
    )


# Track / fetch order status
def track_shipment(
    awb_number: str,
    jf_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:
    """
    GET /api/orders?query_type=track&query_value=<awb>
    """
    action = f"/api/orders?query_type=track&query_value={awb_number}"
    return jf_request("GET", None, action, headers={})


def generate_awb(
    order_ids: list[str], courier_id: str, warehouse_id: str, jf_request: Callable
) -> requests.Response:
    payload = {
        "order_ids": order_ids,
        "courier_id": courier_id,
        "warehouse_id": warehouse_id,
        "async": "false",
    }
    return jf_request("POST", payload, "/orders/ship", headers={})


def list_warehouses(
    jf_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:
    return jf_request("GET", None, "/warehouses", headers={})


def create_warehouse(
    hub,
    jf_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
) -> requests.Response:
    payload = {
        "name": hub.name,
        "person_name": hub.contact_person,
        "phone": hub.phone,
        "email": hub.email,
        "address_1": hub.address_line1,
        "address_2": hub.address_line2,
        "city": hub.city,
        "state": hub.state,
        "country": hub.country,
        "pincode": hub.pin_code,
        "gst_number": hub.gstin,
    }
    return jf_request("POST", payload, "/warehouses", headers={})


# Ship order interface used by central task (same return shape as jiffy.ship_order)
def ship_order(
    order,
    hub,
    courier_abbreviation: str,
    courier_id: str,
    jf_request: Callable[
        [str, Optional[Any], str, Optional[dict], str, str, bool, int, int],
        requests.Response,
    ],
    return_shipment: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Ship an order via Jiffy API.
    Returns (True, response_json) on success; (False, {"error": msg, "response": res_json}) on failure.
    """
    try:
        payload = build_payload(order, hub, return_shipment=return_shipment)
        response = order_booking(payload, jf_request)
        try:
            res_json = response.json()
        except Exception:
            logger.error(
                f"Jiffy non-json response for order {order.id}: {response.text}\nURL:{response.url}"
            )
            return False, {"error": "non-json response", "response_text": response.text}

        if not res_json.get("success"):
            return False, {
                "error": clean_aggregator_or_courier_name(
                    res_json.get("error", {}).get("message", "Unknown error")
                ),
                "response": res_json,
            }
        else:
            # Save to order similar to jiffy implementation
            order.json["order_booking"] = res_json
            order.hub = hub
            try:
                order.logistic_partner = Courier.objects.get(
                    abbreviation=courier_abbreviation
                )
            except Courier.DoesNotExist:
                # fallback: do not crash if courier entry not present
                logger.warning(
                    f"Courier with abbreviation {courier_abbreviation} not found. Leaving logistic_partner unchanged."
                )
                return False, {
                    "error": f"Courier {courier_abbreviation} not found in DB"
                }
            order.save()

        try:
            res_json = list_warehouses(jf_request).json()
            if not res_json.get("success"):
                raise Exception("Failed to fetch warehouses")

            warehouses = res_json.get("data", [])
        except Exception:
            logger.exception("Failed to fetch warehouses from Jiffy")
            return False, {"error": "Failed to fetch warehouses"}

        jiffy_warehouse_id = None
        try:
            for wh in warehouses:
                if wh["name"] == hub.name:
                    jiffy_warehouse_id = wh["id"]
                    break

            if not jiffy_warehouse_id:
                res_json = create_warehouse(hub, jf_request).json()
                if not res_json.get("success"):
                    return False, {
                        "error": clean_aggregator_or_courier_name(
                            res_json.get("error", {}).get("message", "Unknown error")
                        ),
                        "response": res_json,
                    }
                jiffy_warehouse_id = res_json.get("data", {}).get("data", {}).get("id")
        except Exception:
            logger.exception("Failed to update warehouse info")
            return True, {"error": "Failed to create warehouse info"}

        if not jiffy_warehouse_id:
            return True, {"error": "Warehouse ID not found"}

        try:
            order_id = order.json.get("order_booking", {}).get("data", {}).get("id")
            res_json = generate_awb(
                order_ids=[str(order_id)],
                courier_id=courier_id,
                warehouse_id=jiffy_warehouse_id,
                jf_request=jf_request,
            ).json()
            if not res_json.get("success"):
                return False, {
                    "error": clean_aggregator_or_courier_name(
                        res_json.get("error", {}).get("message", "Unknown error")
                    ),
                    "response": res_json,
                }

            if not res_json.get("data", {}).get("success"):
                try:
                    return False, {
                        "error": clean_aggregator_or_courier_name(
                            res_json.get("data", {})
                            .get("results", [])[0]
                            .get("error", "Unknown error in AWB generation")
                        ),
                        "response": res_json,
                    }
                except Exception as e:
                    return False, {
                        "error": f"Unknown error in AWB generation. Exception: {e}",
                        "response": res_json,
                    }

            order.json["awb_generation"] = res_json
            order.awb_number = (
                res_json.get("data", {}).get("results", [])[0].get("awb_number", "")
            )
            order.save()
            order.update_status("pending_pickup")

            return True, res_json
        except Exception:
            logger.exception("Failed to generate AWB")
            return True, {"error": "Failed to generate AWB"}

    except Exception as e:
        logger.exception("Jiffy Ship Order Exception")
        return False, {"error": clean_aggregator_or_courier_name(str(e))}


def bulk_ship_orders(
    orders: list[Order],
    hub,
    courier_abbreviation: str,
    courier_id: str,
    jf_request: Callable,
    return_shipment: bool = False,
) -> Dict[str, Tuple[bool, Dict[str, Any]]]:
    results = {
        "success_orders": [
            # ("order_id", response),
        ],
        "failed_orders": [
            # ("order_id", "error"),
        ],
        "error": None,  # error before processing any orders
    }
    # STEP: 1 - List all warehouses to find the hub warehouse ID
    try:
        res_json = list_warehouses(jf_request).json()
        if not res_json.get("success"):
            results["error"] = (
                f"Failed to fetch warehouses. Error: {clean_aggregator_or_courier_name(res_json.get('error', 'Unknown error'))}"
            )
            return results

        jiffy_warehouses = res_json.get("data", [])
    except Exception as e:
        logger.exception("Failed to fetch warehouses from Jiffy")
        results["error"] = f"Failed to fetch warehouses. Exception: {e}"
        return results

    # STEP: 2 - Find or create the warehouse for the hub
    jiffy_warehouse_id = None
    try:
        for wh in jiffy_warehouses:
            if wh["name"] == hub.name:
                jiffy_warehouse_id = wh["id"]
                break

        if not jiffy_warehouse_id:
            res_json = create_warehouse(hub, jf_request).json()
            if not res_json.get("success"):
                results["error"] = (
                    f"Failed to create warehouse. Error: {clean_aggregator_or_courier_name(res_json.get('error', {}).get('message', 'Unknown error'))}"
                )
                return results

            jiffy_warehouse_id = res_json.get("data", {}).get("data", {}).get("id")
    except Exception as e:
        logger.exception("Failed to update warehouse info")
        results["error"] = f"Failed to create warehouse. Exception: {e}"
        return results

    if not jiffy_warehouse_id:
        results["error"] = "Warehouse ID not found"
        return results

    shipment_data = [
        # (order_obj, shipment_id)
    ]
    for order in orders:
        try:
            payload = build_payload(order, hub, return_shipment=return_shipment)
            if not payload:
                results["failed_orders"].append((order.id, "Failed to build payload"))
                continue

            order_booking_response = order_booking(payload, jf_request).json()
            if not order_booking_response.get("success"):
                results["failed_orders"].append(
                    (
                        order.id,
                        clean_aggregator_or_courier_name(
                            order_booking_response.get("error", {}).get(
                                "message", "Unknown error"
                            )
                        ),
                    )
                )
                order.update_status("ready_to_ship")
                continue

            order.json["order_booking"] = order_booking_response
            order.save()
            shipment_data.append(
                (
                    order,
                    str(order_booking_response.get("data", {}).get("id")),
                )
            )
        except Exception as e:
            logger.exception(f"Failed to book order {order.id}")
            results["failed_orders"].append((order.id, f"Exception: {e}"))
            continue

    # STEP: 3 - Generate AWBs in bulk
    res_json = generate_awb(
        order_ids=[i for _, i in shipment_data],
        courier_id=courier_id,
        warehouse_id=jiffy_warehouse_id,
        jf_request=jf_request,
    ).json()
    if not res_json.get("success"):
        results["error"] = (
            f"Failed to generate AWBs in bulk. Error: {clean_aggregator_or_courier_name(res_json.get('error', {}).get('message', 'Unknown error'))}"
        )
        return results

    logistic_partner = Courier.objects.get(abbreviation=courier_abbreviation)
    # STEP: 4 - Process AWB generation results
    for o_res in res_json.get("data", {}).get("results", []):
        try:
            order_id = o_res.get("order_id")
            order = None
            for i, j in shipment_data:
                if str(j) == str(order_id):
                    order = i
                    break

            if not order:
                results["failed_orders"].append(
                    (order_id, "Order not found in shipment data")
                )
                continue

            if o_res.get("success"):
                order.json["awb_generation"] = res_json
                order.awb_number = o_res.get("awb_number", "")
                order.hub = hub
                order.logistic_partner = logistic_partner
                order.save()
                order.update_status("pending_pickup")
                results["success_orders"].append((order.id, o_res))
            else:
                results["failed_orders"].append(
                    (
                        order.id,
                        clean_aggregator_or_courier_name(
                            o_res.get("error", "Unknown error in AWB generation")
                        ),
                    )
                )
                order.update_status("ready_to_ship")

        except Exception as e:
            logger.exception(
                f"Failed to process AWB generation result for order {order_id}"
            )
            results["failed_orders"].append((order_id, f"Exception: {e}"))
            continue

    return results
