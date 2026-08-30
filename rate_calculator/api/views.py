"""Rate calculator API.

POST /api/calculator/

Request JSON:
    {
        "pickup_pincode": "110001",     # 6 digits, or use "hub_id"
        "hub_id": 12,                    # optional, resolves to that hub's pincode
        "destination_pincode": "400001",
        "weight": 1.2,                   # kg, dead weight (default 0.5)
        "length": 20, "width": 15, "height": 10,   # cm, optional (volumetric)
        "payment_method": "cod",        # or "prepaid" (default)
        "order_value": 1500             # used for COD-percentage charges
    }

Response JSON:
    { "success": true, "zone": "...", "chargeable_weight": 1.2, "data": [ {quote}, ... ] }

Quotes are computed from the requesting merchant's own rate cards (rate cards are
per-user), using the same maths as
order_manager.tasks.calculate_and_debit_shipping_charges.
"""

import json
import logging
import math

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from account.models import RateCard
from order_manager.models import Hub
from order_manager.tasks import detect_zone_from_pincodes
from rate_calculator.services import WeightCalculator

logger = logging.getLogger("my-logger")

GST_RATE_FALLBACK = 0.18


def _err(message, status=400):
    return JsonResponse({"success": False, "error": message}, status=status)


def _valid_pincode(value) -> bool:
    return bool(value) and str(value).isdigit() and len(str(value)) == 6


def _pick_base_weight(weights_sorted: list[float], chargeable: float) -> float:
    for i in range(len(weights_sorted) - 1):
        if weights_sorted[i] <= chargeable < weights_sorted[i + 1]:
            return weights_sorted[i]
    return weights_sorted[-1]


def _quote_for_rate_card(rate_card: RateCard, mode: str, zone: str,
                         chargeable_weight: float, payment_method: str,
                         order_value: float, gst_rate: float) -> dict | None:
    """One courier/mode quote, or None if this rate card can't service it."""
    weights = rate_card.get_available_weights(mode)
    if not weights:
        return None
    try:
        weights_sorted = sorted(float(w) for w in weights)
    except (TypeError, ValueError):
        return None

    base_weight = _pick_base_weight(weights_sorted, chargeable_weight)

    try:
        weight_bracket = rate_card.get_additional_weight(mode=mode, weight=str(base_weight))
    except Exception:
        return None

    try:
        base_charge = rate_card.get_rate(mode, str(base_weight), weight_bracket, zone, "forward", "base")
        additional_charge = rate_card.get_rate(mode, str(base_weight), weight_bracket, zone, "forward", "additional")
        rto_base_charge = rate_card.get_rate(mode, str(base_weight), weight_bracket, zone, "rto", "base")
        rto_additional_charge = rate_card.get_rate(mode, str(base_weight), weight_bracket, zone, "rto", "additional")
    except (KeyError, ValueError):
        return None

    package_weight_grams = int(chargeable_weight * 1000)
    base_weight_in_gm = float(base_weight) * 1000
    weight_bracket_in_gm = float(weight_bracket) * 1000
    additional_weight_gm = max(0, package_weight_grams - base_weight_in_gm)
    additional_units = (
        math.ceil(additional_weight_gm / weight_bracket_in_gm) if weight_bracket_in_gm else 0
    )

    cod_charge = 0.0
    if payment_method == "cod":
        try:
            cod_charge = rate_card.calculate_cod_charges(
                mode=mode, weight=str(base_weight), additional_weight=weight_bracket,
                zone=zone, flow="forward", selling_price=order_value,
            )
        except (KeyError, ValueError):
            cod_charge = 0.0

    additional_charges = additional_units * additional_charge
    forward_before_gst = base_charge + additional_charges + cod_charge
    gst_amount = forward_before_gst * gst_rate
    total = forward_before_gst + gst_amount

    rto_additional = rto_additional_charge * additional_units
    rto_before_gst = rto_base_charge + rto_additional
    rto_gst = rto_before_gst * gst_rate

    courier = rate_card.courier
    eta_map = {
        "within_city": 1, "metro_to_metro": 2, "within_state": 2,
        "rest_of_india": 4, "ne_jk": 5,
    }
    return {
        "courier": courier.name if courier else "",
        "courier_id": courier.id if courier else None,
        "abbreviation": courier.abbreviation if courier else "",
        "rate_card_id": rate_card.id,
        "service_type": mode,
        "zone": zone,
        "chargeable_weight": round(chargeable_weight, 2),
        "estimated_days": eta_map.get(zone, 5),
        "rate": {
            "base": round(base_charge, 2),
            "additional": round(additional_charges, 2),
            "cod": round(cod_charge, 2),
            "gst": round(gst_amount, 2),
            "total": round(total, 2),
            "rto_base": round(rto_base_charge, 2),
            "rto_additional": round(rto_additional, 2),
            "rto_gst": round(rto_gst, 2),
            "rto_total": round(rto_before_gst + rto_gst, 2),
        },
    }


@require_POST
def rate_calculator(request):
    if not request.user.is_authenticated:
        return _err("Authentication required.", status=401)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _err("Invalid JSON")

    gst_rate = float(getattr(settings, "GST_ON_SHIPMENT", GST_RATE_FALLBACK))

    pickup_pincode = str(data.get("pickup_pincode") or "").strip()
    hub_id = data.get("hub_id")
    destination_pincode = str(data.get("destination_pincode") or "").strip()

    if hub_id:
        hub = Hub.objects.filter(user=request.user, id=hub_id, is_active=True).first()
        if not hub:
            return _err("Invalid hub_id", status=422)
        pickup_pincode = str(hub.pin_code)

    if not _valid_pincode(pickup_pincode):
        return _err("Invalid pickup pincode. Must be 6 digits.")
    if not _valid_pincode(destination_pincode):
        return _err("Invalid destination pincode. Must be 6 digits.")

    try:
        weight = float(data.get("weight", 0.5))
    except (TypeError, ValueError):
        return _err("Invalid weight")
    if weight < 0.5:
        return _err("Minimum weight must be 0.5kg")

    length, width, height = data.get("length"), data.get("width"), data.get("height")
    chargeable_weight = WeightCalculator.calculate_chargeable_weight(
        weight, length, width, height
    )

    payment_method = (data.get("payment_method") or "prepaid").lower()
    try:
        order_value = float(data.get("order_value", 0) or 0)
    except (TypeError, ValueError):
        order_value = 0.0

    zone = detect_zone_from_pincodes(pickup_pincode, destination_pincode)

    rate_cards = (
        RateCard.objects.filter(user=request.user, courier__active=True)
        .select_related("courier")
    )

    results: list[dict] = []
    for rate_card in rate_cards:
        modes = rate_card.get_available_modes() or ["surface"]
        for mode in modes:
            try:
                quote = _quote_for_rate_card(
                    rate_card, mode, zone, chargeable_weight,
                    payment_method, order_value, gst_rate,
                )
            except Exception:
                logger.exception(
                    "rate_calculator: quote failed for rate_card %s mode %s",
                    rate_card.id, mode,
                )
                quote = None
            if quote:
                results.append(quote)

    results.sort(key=lambda q: q["rate"]["total"])

    return JsonResponse({
        "success": True,
        "zone": zone,
        "chargeable_weight": round(chargeable_weight, 2),
        "data": results,
    })
