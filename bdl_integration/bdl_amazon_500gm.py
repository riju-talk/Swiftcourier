import logging
import requests

from typing import Dict, Any, Tuple

from order_manager.models import Order
from . import common


logger = logging.getLogger("my-logger")


# Waybill generation (order booking)
def order_booking(shipment_data: Dict[str, Any]) -> requests.Response:
    common.order_booking(shipment_data)


# Cancel order (POST /cancel)
def cancel_shipment(waybill: str) -> requests.Response:
    return common.cancel_shipment(waybill)


# Track / fetch order status
def track_shipment(awb_number: str) -> requests.Response:
    """
    GET /api/orders?query_type=track&query_value=<awb>
    """
    return common.track_shipment(awb_number)


def generate_label(
    orders: list[Order],
) -> tuple[Exception | bool, str | None]:
    return common.generate_label(orders)


# Ship order interface used by central task (same return shape as ship_order)
def ship_order(
    order, hub, return_shipment: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Ship an order via BDL API.
    Returns (True, response_json) on success; (False, {"error": msg, "response": res_json}) on failure.
    """
    return common.ship_order(order, hub, "bdl_ats_surface_500gm", "19", return_shipment)


def bulk_ship_orders(orders, hub):
    return common.bulk_ship_orders(
        orders=orders,
        hub=hub,
        courier_abbreviation="bdl_ats_surface_500gm",
        courier_id="19",
    )
