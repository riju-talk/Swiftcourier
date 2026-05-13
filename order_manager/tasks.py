import logging
import math
import uuid
import requests

from typing import Optional, Tuple
from functools import lru_cache
from celery import shared_task
from collections import defaultdict

from django.conf import settings
from django.utils.timezone import now
from django.db.models.query import QuerySet

from account.models import Courier, User, RateCard, Notification
from order_manager.models import Hub, Order
from wallet.models import Transaction
from utils.get_courier_handler import get_courier_handler


logger = logging.getLogger("my-logger")


def ship_orders_by_preference(
    order_ids: list[int],
    hub_id: int,
    user_id: int,
    auto_fetch_courier_preference: bool = True,
    courier_preference: list[int] | None = None,
):
    pass


def unlock_orders(orders: list[Order]):
    """
    Unlock orders by setting is_locked to False.
    """
    for order in orders:
        try:
            order.update_status("ready_to_ship")
        except:
            pass


def fetch_location(pincode: str) -> Tuple[str, str]:
    """
    Fetch and return (city, state) for a given PIN code using India Post API.
    """
    url = f"https://api.postalpincode.in/pincode/{pincode}"
    resp = requests.get(url)
    data = resp.json()
    if not data or data[0].get("Status") != "Success":
        raise ValueError(f"Invalid PIN code or API failure: {pincode}")

    post_office = data[0]["PostOffice"][0]
    city = post_office.get("District", "") or post_office.get("Name", "")
    state = post_office.get("State", "")
    return city.strip().lower(), state.strip().lower()


@lru_cache(maxsize=1000)
def detect_zone_from_pincodes(pickup_pin: str, dest_pin: str, country="india") -> str:
    """
    Determine shipping zone between two Indian PIN codes.

    Zones:
      - "within_city"
      - "metro_to_metro"
      - "ne_jk"
      - "within_state"
      - "rest_of_india"
    """

    # Include common synonyms and district variants for metro cities
    METRO_CITIES = {
        "delhi",
        "new delhi",
        "north delhi",
        "south delhi",
        "mumbai",
        "greater mumbai",
        "kolkata",
        "calcutta",
        "chennai",
        "bengaluru",
        "bangalore",
        "bengaluru urban",
        "bangalore urban",
        "hyderabad",
    }
    NE_JK_STATES = {
        "assam",
        "arunachal pradesh",
        "manipur",
        "meghalaya",
        "mizoram",
        "nagaland",
        "tripura",
        "sikkim",
        "jammu and kashmir",
        "jammu & kashmir",
    }

    def is_metro(city: str) -> bool:
        """
        Determine if a city string belongs to a metro area, using substring match against synonyms.
        """
        for metro in METRO_CITIES:
            if metro in city:
                return True
        return False

    def normalize_name(name: str) -> str:
        """
        Normalize names: lowercase, replace '&' with 'and', collapse whitespace.
        """
        s = name.strip().lower()
        s = s.replace("&", "and")
        return " ".join(s.split())

    try:
        # Fetch raw values
        p_city_raw, p_state_raw = fetch_location(pickup_pin)
        d_city_raw, d_state_raw = fetch_location(dest_pin)

        # Normalize
        p_city = normalize_name(p_city_raw)
        d_city = normalize_name(d_city_raw)
        p_state = normalize_name(p_state_raw)
        d_state = normalize_name(d_state_raw)

        # 1. Same city
        if p_city == d_city:
            return "within_city"

        # 2. Both metro cities
        if is_metro(p_city) and is_metro(d_city):
            return "metro_to_metro"

        # 3. Any in NE or JK
        if p_state in NE_JK_STATES or d_state in NE_JK_STATES:
            return "ne_jk"

        # 4. Same state
        if p_state == d_state:
            return "within_state"

        # 5. Everything else
        return "rest_of_india"
    except Exception:
        return "rest_of_india"


def calculate_and_debit_shipping_charges(
    orders: QuerySet[Order],
    hub: Hub,
    shipping_mode: str,
    rate_card: RateCard,
    user: User,
) -> dict:
    result = {
        "success": [
            # (order, shipping_charges)
        ],
        "failed": [
            # (order_id, reason)
        ],
    }
    total_order_count = orders.count()
    for order in orders:
        zone = detect_zone_from_pincodes(
            pickup_pin=hub.pin_code,
            dest_pin=order.shipping_address.pin_code,
        )
        order.json["detected_zone"] = zone
        order.save()

        # Calculate weight in kg
        package_weight_kg = order.shipment.package_weight_kg
        try:
            volutmetric_weight_in_kg = (
                order.shipment.package_length_cm
                * order.shipment.package_width_cm
                * order.shipment.package_height_cm
            ) / 5000
            order.shipment.volumetric_weight_kg = volutmetric_weight_in_kg
            order.shipment.save()
            if volutmetric_weight_in_kg > package_weight_kg:
                package_weight_kg = volutmetric_weight_in_kg
        except:
            logger.exception("Getting error:")

        package_weight_grams = int(package_weight_kg * 1000)
        # sort available weights in descending order
        weights = rate_card.get_available_weights(shipping_mode)
        weights_sorted = sorted(weights, key=lambda x: round(float(x), 2))

        for i in range(len(weights_sorted) - 1):
            if (
                float(weights_sorted[i])
                <= package_weight_kg
                < float(weights_sorted[i + 1])
            ):
                base_weight = weights_sorted[i]
                break
        else:
            base_weight = weights_sorted[-1]

        base_weight_in_gm = float(base_weight) * 1000

        try:
            weight_bracket = rate_card.get_additional_weight(
                mode=shipping_mode, weight=base_weight
            )
        except Exception as e:
            logger.exception(f"Failed to get additional weight for order {order.id}: ")
            result["failed"].append(
                (order.id, "Failed to get Addtional Weight"),
            )
            order.update_status("ready_to_ship")
            continue

        try:
            base_charge = rate_card.get_rate(
                mode=shipping_mode,
                weight=str(base_weight),
                additional_weight=weight_bracket,
                zone=zone,
                flow="forward",
                kind="base",
            )
            additional_charge = rate_card.get_rate(
                mode=shipping_mode,
                weight=str(base_weight),
                additional_weight=weight_bracket,
                zone=zone,
                flow="forward",
                kind="additional",
            )
            rto_base_charge = rate_card.get_rate(
                mode=shipping_mode,
                weight=str(base_weight),
                additional_weight=weight_bracket,
                zone=zone,
                flow="rto",
                kind="base",
            )
            rto_additional_charge = rate_card.get_rate(
                mode=shipping_mode,
                weight=str(base_weight),
                additional_weight=weight_bracket,
                zone=zone,
                flow="rto",
                kind="additional",
            )

        except KeyError:
            result["failed"].append(
                (order.id, "Failed while calculating shipping charges")
            )
            order.update_status("ready_to_ship")
            continue

        weight_bracket_in_gm = float(weight_bracket) * 1000
        additional_weight = max(0, package_weight_grams - base_weight_in_gm)
        additional_units = math.ceil(additional_weight / weight_bracket_in_gm)

        cod_charge = 0
        if order.payment.method == "cod":
            cod_charge = rate_card.calculate_cod_charges(
                mode=shipping_mode,
                weight=str(base_weight),
                additional_weight=weight_bracket,
                zone=zone,
                flow="forward",
                selling_price=order.total_amount,
            )

        additional_charges = additional_units * additional_charge
        total_shipping_charges = base_charge + additional_charges + cod_charge
        gst_amount = total_shipping_charges * settings.GST_ON_SHIPMENT
        total_shipping_charges += gst_amount

        final_rto_additional_charge = rto_additional_charge * additional_units
        rto_charges = rto_base_charge + final_rto_additional_charge
        rto_gst_amount = rto_charges * settings.GST_ON_SHIPMENT
        rto_charges += rto_gst_amount

        # before updating see rto charges cutting logic
        order.payment.price_breakup = {
            "base_charge": base_charge,
            "additional_charges": additional_charges,
            "cod_charge": cod_charge,
            "gst_amount": gst_amount,
            # --- RTO ---
            "rto_base_charge": rto_base_charge,
            "rto_additional_charge": final_rto_additional_charge,
            "rto_gst_amount": rto_gst_amount,
            "rto_charges": rto_charges,
        }
        order.payment.shipping_charges = total_shipping_charges
        order.payment.cod_charges = cod_charge
        order.payment.tax_percent = settings.GST_ON_SHIPMENT * 100
        order.payment.save()

        try:
            order.json["rate_card_details"] = {
                "id": rate_card.id,
                "mode": shipping_mode,
                "base_weight": str(base_weight),
                "addl_weight": str(weight_bracket),
                "zone": zone,
                "courier_name": rate_card.courier.abbreviation,
                "json": rate_card.data,
            }
            order.save()
        except Exception:
            pass

        trsn = Transaction.create_transaction(
            user=user,
            merchant_txn_id=str(order.id) + "_" + str(uuid.uuid4()),
            amount_rs=total_shipping_charges,
            desc="shipping_charges",
            transaction_type="debit",
        )
        logger.debug("Transaction init...")
        if not trsn.debit(awb_number=order.awb_number):
            logger.error("Transaction failed...")
            result["failed"].append(
                (
                    order.id,
                    f"Failed to debit shipping charges for order {order.id}.",
                )
            )
            order.update_status("ready_to_ship")
            continue

        logger.debug("Transaction done.....")

        result["success"].append((order, total_shipping_charges))

    return result


def bulk_cancel_orders_by_courier_handler(
    courier_handler, order_ids: list[str], hub: Hub | None = None
):
    if hasattr(courier_handler, "cancel_bulk_orders"):
        orders = Order.objects.filter(
            id__in=order_ids,
        )
        for o in orders:
            o.update_status("ready_to_ship")
        cancel_res = courier_handler.cancel_bulk_orders(
            orders,
            hub,
        )
    else:
        for order_id in order_ids:
            try:
                o = Order.objects.get(id=order_id)
                o.update_status("ready_to_ship")
                cancel_res = courier_handler.cancel_order(
                    o,
                    hub,
                )
            except:
                pass


@shared_task
def bulk_cancel_orders(order_ids: list[int], user_id: int):
    qs = Order.objects.filter(
        id__in=order_ids,
        user__id=user_id,
    ).select_related("logistic_partner", "payment")

    # -------- Group by courier --------
    orders_by_courier = defaultdict(list)
    for order in qs:
        if order.logistic_partner:
            orders_by_courier[order.logistic_partner].append(order)

    # -------- Process each courier --------
    for courier in orders_by_courier:
        orders = orders_by_courier[courier]
        try:
            courier_handler = get_courier_handler(courier)
            if not courier_handler:
                continue

            try:
                try:
                    # ---- Call API ----
                    if hasattr(courier_handler, "cancel_bulk_orders"):
                        courier_handler.cancel_bulk_orders(orders)
                    else:
                        for order in orders:
                            courier_handler.cancel_shipment(order)
                except:
                    pass

                logger.debug("Updating order....")
                # ---- Update in-memory objects ----
                updated_orders = []
                for order in orders:
                    err = _refund_and_prepare_cancel(order)
                    if err:
                        logger.debug(
                            f"Failed to credit amount for order id: {order.id}"
                        )
                    else:
                        updated_orders.append(order)

                # ---- Bulk DB update (🔥 major optimization) ----
                Order.objects.bulk_update(
                    updated_orders,
                    ["status", "cancel_data"],
                )

            except Exception as e:
                logger.error(f"Courier cancel failed: {courier} | {e}")
                continue

        except Exception as e:
            logger.error(f"Handler error: {courier} | {e}")
            continue

    return True


def _refund_and_prepare_cancel(order: Order) -> bool:
    """Return Error"""
    # -------- Transaction (cannot bulk, keep as-is) --------
    tr = Transaction.create_transaction(
        user=order.user,
        merchant_txn_id=f"{order.id}_cancel_{uuid.uuid4()}",
        amount_rs=order.payment.shipping_charges,
        desc="cancelled_order",
        transaction_type="credit",
    )
    if not tr.credit(awb_number=order.awb_number):
        return ValueError("Failed to credit amount")

    # -------- Avoid repeated dict writes --------
    if not order.cancel_data:
        order.cancel_data = {}

    order.cancel_data[str(order.awb_number)] = {
        "cancelled_at": now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "courier": (
            f"{order.logistic_partner.name} ({order.logistic_partner.abbreviation})"
            if order.logistic_partner
            else "N/A"
        ),
        "refund_amount": order.payment.shipping_charges,
    }
    return False


@shared_task
def ship_orders(
    order_ids: list[int],
    hub_id: int,
    user_id: int,
    courier_id: int,
    rate_card_id: int,
    mode: str = "surface",
) -> dict:
    result = {
        "count": {
            "success": 0,
            "failed": 0,
        },
        "error_message": [],
    }
    try:
        user = User.objects.get(id=user_id)
        hub = Hub.objects.get(id=hub_id)
        courier = Courier.objects.get(id=courier_id)
        rate_card: RateCard = RateCard.objects.filter(id=rate_card_id).first()
        courier_handler = get_courier_handler(courier)
    except:
        result["count"]["failed"] = len(order_ids)
        result["error_message"].append("Error in fetching details for shipping")
        return result

    orders = Order.objects.filter(id__in=order_ids).select_related(
        "shipping_address", "payment", "shipment"
    )

    try:
        shipping_mode = courier.available_modes[0]
    except IndexError:
        shipping_mode = mode

    if hasattr(courier_handler, "bulk_ship_orders"):
        res_from_aggr = courier_handler.bulk_ship_orders(orders, hub)
        if res_error := res_from_aggr.get("error"):
            orders.update(status="ready_to_ship")
            Notification.objects.create(
                category="info",
                msg=f"Failed to ship orders. Error: {res_error}",
                user=user,
            )
            return result

        success_orders_from_aggr = res_from_aggr.get("success_orders")
        if success_orders_from_aggr:
            res_of_shipping_charges = calculate_and_debit_shipping_charges(
                orders=Order.objects.filter(
                    id__in=[order_id for order_id, _ in success_orders_from_aggr]
                ),
                hub=hub,
                shipping_mode=shipping_mode,
                rate_card=rate_card,
                user=user,
            )
            logger.debug(f"Res of shipping chages: {res_of_shipping_charges}")

            success_orders = res_of_shipping_charges["success"]
            failed_orders = res_of_shipping_charges["failed"]
            if failed_orders:
                try:
                    canel_res_from_aggr = bulk_cancel_orders_by_courier_handler(
                        courier_handler=courier_handler,
                        order_ids=[order_id for order_id, _ in failed_orders],
                        hub=hub,
                    )
                except Exception as e:
                    logger.exception("Error in cancel response: ")
                result["error_message"].append(f"Wallet is low")

        try:
            result["error_message"].extend(
                [j for _, j in res_from_aggr.get("failed_orders", [])]
            )
            result["count"]["failed"] = len(result["error_message"])
        except Exception as e:
            result["error_message"].append(f"Error while fetching errors. Error: {e}")

        try:
            result["count"]["success"] = len(success_orders)
        except:
            pass

    else:
        result["count"]["failed"] = orders.count()
        result["error_message"].append("Failed to ship order. Error Code: ERR5001")
        orders.update(status="ready_to_ship")
        # for order in orders:
        #     try:
        #         success, err = courier_handler.ship_order(order, hub)
        #         if success:
        #             result["count"]["success"] += 1
        #         else:
        #             result["count"]["failed"] += 1
        #             err = err.get("error", "Unknown error")
        #             result["error_message"].append(f"Order ID {order.id}: {str(err)}")
        #     except Exception as e:
        #         result["count"]["failed"] += 1
        #         result["error_message"].append(f"Order ID {order.id}: {str(e)}")

    error_msg = (
        " ||| ".join(result["error_message"])
        if result["error_message"]
        else "All orders shipped successfully."
    )

    try:
        n = Notification.objects.create(
            category="info",
            msg=f"Shipped Orders. Success: {result['count']['success']} Failed: {result['count']['failed']}.\n{error_msg}",
            user=user,
        )
    except Exception as e:
        logger.exception("Got: ")

    return result
