import requests
import logging
from typing import Dict, Any, Optional, Tuple

from order_manager.models import Order

from . import common


logger = logging.getLogger("my-logger")


# Waybill generation (order booking)
def order_booking(shipment_data: Dict[str, Any]) -> requests.Response:
    common.order_booking(shipment_data)


# Cancel order (POST /cancel)
def cancel_shipment(waybill: str) -> requests.Response:
    return common.cancel_shipment(waybill)


def cancel_bulk_orders(orders: list[Order], hub):
    return common.cancel_bulk_orders(orders=orders)


# Track / fetch order status
def track_shipment(awb_number: str) -> requests.Response:
    """
    GET /api/orders?query_type=track&query_value=<awb>
    """
    return common.track_shipment(awb_number)


def generate_label(
    orders: list[Order],
) -> requests.Response:
    return common.generate_label(orders)


# Ship order interface used by central task (same return shape as ship_order)
def ship_order(
    order, hub, return_shipment: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Ship an order via Fship API.
    Returns (True, response_json) on success; (False, {"error": msg, "response": res_json}) on failure.
    """
    return common.ship_order(
        order,
        hub,
        "rsn_ats_1kg",
        "8002",
        return_shipment,
        shipment_weight=0.5,
    )


def bulk_ship_orders(orders, hub):
    return common.bulk_ship_orders(
        orders=orders,
        hub=hub,
        courier_abbreviation="rsn_ats_1kg",
        courier_id="8002",
        shipment_weight=0.5,
    )
