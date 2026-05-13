import logging
import traceback
from typing import Tuple
import uuid
from functools import lru_cache

from django.conf import settings
from django.utils.timezone import now
from django_tasks import task
import requests

from account.models import BlockedPincode, Courier, User, RateCard
from order_manager.models import Hub, Order
from wallet.models import Transaction
from utils.get_courier_handler import get_courier_handler

from account.models import (
    Notification,
)


logger = logging.getLogger("my-logger")


# def get_courier_handler(courier: Courier):
#     module = importlib.import_module(courier.integration_path)
#     return module


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


@task
def ship_orders(
    order_ids: list[int],
    hub_id: int,
    user_id: int,
    courier_id: int,
    rate_card_id: int,
    mode: str = "surface",
) -> dict:
    """
    Task to ship orders based on the provided order IDs.

    :param order_ids: List of order IDs to be shipped.
    :param hub: The hub from which the orders will be shipped.
    """
    user = User.objects.filter(id=user_id).first()
    hub = Hub.objects.filter(id=hub_id).first()
    courier = Courier.objects.get(id=courier_id)
    rate_card: RateCard = RateCard.objects.filter(id=rate_card_id).first()
    courier_handler = get_courier_handler(courier)

    result = {
        "count": {
            "success": 0,
            "failed": 0,
        },
        "error_message": [],
    }

    # orders = []
    # for order_id in order_ids:
    #     try:
    #         o = Order.objects.get(id=order_id, user=user, status="ready_to_ship")
    #     except Order.DoesNotExist:
    #         result["error_message"].append(
    #             f"Order with id {order_id} does not exist or is not ready to ship."
    #         )
    #         result["count"]["failed"] += 1
    #         continue
    #     if not o.is_locked:
    #         try:
    #             # o.lock_order()
    #             orders.append(o)
    #         except Exception as e:
    #             logger.error(f"Failed to lock order {o.id}: {e}")
    orders = Order.objects.filter(id__in=order_ids).select_related(
        "shipping_address", "payment", "shipment", "payment"
    )
    errors = result["error_message"]

    shipping_data = [
        # (order_obj, total_shipping_charges)
    ]
    try:
        shipping_mode = courier.available_modes[0]
    except IndexError:
        shipping_mode = mode

    for order in orders:
        zone = detect_zone_from_pincodes(
            pickup_pin=hub.pin_code,
            dest_pin=order.shipping_address.pin_code,
        )

        order.json["detected_zone"] = zone
        order.save()
        package_weight_kg = order.shipment.package_weight_kg
        # Calculate weight in grams
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
            result["count"]["failed"] += 1
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
            logger.exception(f"Failed to get rates for order {order.id}: ")
            result["count"]["failed"] += 1
            order.update_status("ready_to_ship")
            continue

        weight_bracket_in_gm = float(weight_bracket) * 1000
        additional_weight = max(0, package_weight_grams - base_weight_in_gm)
        additional_units = additional_weight // weight_bracket_in_gm

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

        rto_charges = rto_base_charge + rto_additional_charge
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
            "rto_additional_charge": rto_additional_charge,
            "rto_gst_amount": rto_gst_amount,
            "rto_charges": rto_charges,
        }
        order.payment.shipping_charges = total_shipping_charges
        order.payment.cod_charges = cod_charge
        order.payment.tax_percent = settings.GST_ON_SHIPMENT * 100
        order.payment.save()

        shipping_data.append((order, total_shipping_charges))

        try:
            order.json["rate_card_details"] = {
                "id": rate_card_id,
                "mode": mode,
                "base_weight": str(base_weight),
                "addl_weight": str(weight_bracket),
                "zone": zone,
                "courier_name": rate_card.courier.abbreviation,
                "json": rate_card.data,
            }
            order.save()
        except Exception as e:
            logger.exception(f"Error while saving rate_card_details")

    if hasattr(courier_handler, "bulk_ship_order"):
        required_amount = sum([j for _, j in shipping_data])
        orders_to_ship = [i for i, _ in shipping_data]
        if not user.have_balance(required_amount):
            errors.append(
                f"Insufficient balance for user '{user.full_name}' to ship orders: {orders_to_ship}. Required: {required_amount}, Available: {user.balance}."
            )
            result["count"]["failed"] += 1

        res = courier_handler.bulk_ship_orders(orders_to_ship, hub)
        if res_error := res.get("error"):
            logger.error(f"Error shipping bulk order: {res_error}")
            Notification.objects.create(
                category="info",
                msg=f"Failed to ship orders. Error: {res_error}",
                user=user,
            )
            unlock_orders(orders_to_ship)
            return result

        result["count"]["success"] = len(res.get("success_orders", []))
        result["count"]["failed"] = len(res.get("failed_orders", []))

        try:
            result["error_message"] = [j for _, j in res.get("failed_orders", [])]
        except Exception as e:
            logger.exception("Error while fetching errors")
            res["error_message"] = f"Error while fetching errors. Error: {e}"

        for o, shipping_amount in shipping_data:
            trsn = Transaction.create_transaction(
                user=user,
                merchant_txn_id=str(o.id) + "_" + str(uuid.uuid4()),
                amount_rs=shipping_amount,
                desc="shipping_charges",
                transaction_type="debit",
            )
            if not trsn.debit(awb_number=o.awb_number):
                errors.append(
                    f"Failed to debit shipping charges for order {o.id} from user {user.username}."
                )
                o.update_status("ready_to_ship")
                continue

            o.payment.transaction = trsn
            o.payment.amount = total_shipping_charges
            o.payment.save()

            o.shipment.booked_at = now()
            o.shipment.save()

            o.update_status("pending_pickup")
    else:
        for order, total_shipping_charges in shipping_data:
            # Check if user has sufficient balance
            if not user.have_balance(total_shipping_charges):
                errors.append(
                    f"Insufficient balance for user '{user.full_name}' to ship order no: #{order.id}. Required: {total_shipping_charges}, Available: {user.balance}."
                )
                result["count"]["failed"] += 1
                break

            success, error = courier_handler.ship_order(order, hub)
            if success:
                result["count"]["success"] += 1

                trsn = Transaction.create_transaction(
                    user=user,
                    merchant_txn_id=str(order.id) + "_" + str(uuid.uuid4()),
                    amount_rs=total_shipping_charges,
                    desc="shipping_charges",
                    transaction_type="debit",
                )
                if not trsn.debit(awb_number=order.awb_number):
                    errors.append(
                        f"Failed to debit shipping charges for order {order.id} from user {user.username}."
                    )
                    order.update_status("ready_to_ship")
                    continue

                order.payment.transaction = trsn
                order.payment.amount = total_shipping_charges
                order.payment.save()

                order.shipment.booked_at = now()
                order.shipment.save()
                order.update_status("pending_pickup")
            else:
                error_msg = error.get("error", "Unknown error")
                errors.append(
                    f"{courier.name} Order Booking Failed for order id {order.id}\tError: {error_msg}"
                )
                order.update_status("ready_to_ship")
                result["count"]["failed"] += 1

        # for order in orders:
        #     order.update_status("ready_to_ship")

    error_msg = " ||| ".join(errors) if errors else "All orders shipped successfully."

    n = Notification(
        category="info",
        msg=f"Shipped Orders. Success: {result['count']['success']} Failed: {result['count']['failed']}.\n{error_msg}",
        user=user,
    )
    n.save()

    return result
