import math
from collections import defaultdict
from django.conf import settings

orders = (
    Order.objects.filter(user__email="onlineindustryshopip@gmail.com")
    .exclude(status__in=["ready_to_ship", "cancelled", "processing"])
    .select_related("shipment", "payment")
)

debit_note = []
total_extra = 0

for o in orders:
    shipment = o.shipment
    payment = o.payment
    normal_weight = shipment.package_weight_kg
    vol_weight = (
        shipment.package_length_cm
        * shipment.package_width_cm
        * shipment.package_height_cm
    ) / 5000
    if vol_weight <= normal_weight:
        continue  # no underpayment
    billable_weight = vol_weight  # vol is higher
    # What was actually charged (before GST)
    already_charged = payment.shipping_charges  # includes GST
    # Get rate card details stored on order
    rc_details = o.json.get("rate_card_details", {})
    if not rc_details:
        print(f"Order {o.id}: No rate card details found, skipping")
        continue
    rate_card = RateCard.objects.filter(id=rc_details["id"]).first()
    if not rate_card:
        continue
    mode = rc_details["mode"]
    zone = rc_details["zone"]
    # Recalculate correct charges using vol weight
    weights = rate_card.get_available_weights(mode)
    weights_sorted = sorted(weights, key=lambda x: round(float(x), 2))
    base_weight = weights_sorted[0]  # min weight slab
    base_weight_in_gm = float(base_weight) * 1000
    billable_weight_grams = int(billable_weight * 1000)
    weight_bracket = rate_card.get_additional_weight(mode=mode, weight=base_weight)
    weight_bracket_in_gm = float(weight_bracket) * 1000
    base_charge = rate_card.get_rate(
        mode=mode,
        weight=str(base_weight),
        additional_weight=weight_bracket,
        zone=zone,
        flow="forward",
        kind="base",
    )
    additional_charge = rate_card.get_rate(
        mode=mode,
        weight=str(base_weight),
        additional_weight=weight_bracket,
        zone=zone,
        flow="forward",
        kind="additional",
    )
    additional_weight = max(0, billable_weight_grams - base_weight_in_gm)
    additional_units = math.ceil(additional_weight / weight_bracket_in_gm)
    correct_charge = base_charge + (additional_units * additional_charge)
    gst = correct_charge * settings.GST_ON_SHIPMENT
    correct_charge_with_gst = correct_charge + gst
    extra = round(correct_charge_with_gst - already_charged, 2)
    if extra > 0:
        total_extra += extra
        debit_note.append(
            {
                "order_id": o.id,
                "normal_weight_kg": normal_weight,
                "vol_weight_kg": round(vol_weight, 3),
                "charged_amount": already_charged,
                "correct_amount": round(correct_charge_with_gst, 2),
                "extra_to_debit": extra,
            }
        )

print(f"\nTotal orders with underpayment: {len(debit_note)}")
print(f"Total extra to debit: ₹{round(total_extra, 2)}\n")

for row in debit_note:
    print(row)
