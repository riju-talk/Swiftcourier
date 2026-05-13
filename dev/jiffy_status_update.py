from datetime import datetime
from django.utils.timezone import make_aware

data = {
}



orders = Order.objects.select_related("shipment").filter(
    logistic_partner__abbreviation__startswith="jf", awb_number__in=data.keys()
)

status_map = {
    "new": "pending_pickup",
    "booked": "pending_pickup",
    "pending pickup": "pending_pickup",
    "in transit": "in_transit",
    "out for delivery": "out_for_delivery",
    "exception": "exception",
    "delivered": "delivered",
    "rto in transit": "rto_in_transit",
    "rto delivered": "rto_delivered",
    "lost": "lost",
    "damaged": "damaged",
    "cancelled": "cancelled",
}


def parse_delivery_date(date_str):
    """
    Supports dd/mm/yyyy and mm/dd/yyyy
    """
    day, month, year = map(int, date_str.split("/"))
    fmt = "%m/%d/%Y"
    return make_aware(datetime.strptime(date_str, fmt))


for i in orders:
    try:
        details = data.get(i.awb_number)
        if not details:
            continue
        old_status = i.status
        raw_status = details[0].lower().strip()
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
