import json
import logging
from typing import Dict, Any, Optional, Tuple

import requests
from django.conf import settings

from account import creds
from order_manager.models import Order
from . import common

logger = logging.getLogger("my-logger")


# Waybill generation (order booking)
def order_booking(shipment_data: Dict[str, Any]) -> requests.Response:
    common.order_booking(shipment_data)


# Cancel order (POST /cancel)
def cancel_shipment(waybill: str) -> requests.Response:
    return common.cancel_shipment(waybill)


def cancel_bulk_orders(orders: list[Order], hub = None):
    return common.cancel_bulk_orders(orders=orders)


# Track / fetch order status
def track_shipment(awb_number: str) -> requests.Response:
    """
    GET /api/orders?query_type=track&query_value=<awb>
    """
    return common.track_shipment(awb_number)


# Ship order interface used by central task (same return shape as ship_order)
def ship_order(
    order, hub, return_shipment: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Ship an order via Fship API.
    Returns (True, response_json) on success; (False, {"error": msg, "response": res_json}) on failure.
    """
    return common.ship_order(order, hub, "ss_bd_1kg", "398", return_shipment)


def bulk_ship_orders(orders, hub):
    return common.bulk_ship_orders(
        orders=orders,
        hub=hub,
        courier_abbreviation="ss_bd_1kg",
        courier_id="398",
    )
