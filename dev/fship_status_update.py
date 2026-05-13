from datetime import datetime
from django.utils.timezone import make_aware

data = {
"SF3267197926FXS":["Pickup Completed", ""],
"14344961555868":["In Transit", ""],
"37355836666500":["In Transit", ""],
"37355836666496":["In Transit", ""],
"37355836666485":["In Transit", ""],
"37355836666474":["In Transit", ""],
"37355836666463":["In Transit", ""],
"SF3267201024FXS":["In Transit", ""],
"37355836630634":["In Transit", ""],
"14344961544959":["In Transit", ""],
}


orders = Order.objects.select_related("shipment").filter(
    logistic_partner__abbreviation__startswith="fs_", awb_number__in=data.keys()
)

status_map = {
    "Booked": "pending_pickup",
    "Delivered": "delivered",
    "In Transit": "in_transit",
    "New": "pending_pickup",
    "Order Cancelled": "cancelled",
    "Out For Pickup": "pending_pickup",
    "Out For Delivery": "out_for_delivery",
    "Pickup Complete": "in_transit",
    "Pickup Initiated": "pending_pickup",
    "Pickup Pending": "pending_pickup",
    "Undelivered": "ndr",
    "RTO": "ndr",
    "RTO Delivered": "rto_delivered",
    "RTO In Transit": "rto_in_transit",
}


def parse_delivery_date(date_str):
    """
    Supports dd-mm-yyyy and mm-dd-yyyy
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    formats = ["%m-%d-%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return make_aware(dt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: {date_str}")


for i in orders:
    try:
        details = data.get(i.awb_number)
        if not details:
            continue
        old_status = i.status
        raw_status = details[0].strip()
        new_status = status_map.get(raw_status)
        if not new_status:
            print(f"Unknown status '{details[0]}' for AWB {i.awb_number}")
            continue
        if old_status != new_status:
            i.status = new_status
            i.save(update_fields=["status"])
        if new_status in ["delivered", "rto_delivered"] and len(details) > 1:
            if i.shipment:
                try:
                    delivered_dt = parse_delivery_date(details[1])
                    i.shipment.delivered_at = delivered_dt
                    i.shipment.save(update_fields=["delivered_at"])
                except Exception as e:
                    print(f"Error in delivery date, error: {e}")
        print(
            f"Order {i.awb_number} status updated " f"from {old_status} to {new_status}"
        )
    except Exception as e:
        print(f"Error processing order {i.awb_number}: {e}")
        continue
