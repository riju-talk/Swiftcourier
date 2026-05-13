import csv
from django.db.models.functions import TruncDate
from django.utils.timezone import now
from datetime import datetime
from django.utils import timezone

start_date = timezone.make_aware(datetime(2025, 12, 31))

orders = (
    Order.objects.filter(
        shipment__booked_at__gte=start_date,
        shipment__booked_at__lte=now(),
    )
    .annotate(o_date=TruncDate("shipment__booked_at"))
    .values(
        "o_date",
        "user__id",
        "user__full_name",
        "awb_number",
        "logistic_partner__name",
        "status",
    )
    .order_by("user__id")
)

with open("test.csv", "w") as f:
    w = csv.writer(f)
    w.writerow([
        "Order Date","User Name","User ID","AWB Number","Logistic Partner","Order Status"
    ])
    for row in orders:
        w.writerow([
            row["o_date"],
            row["user__full_name"],
            row["user__id"],
            row["awb_number"],
            row["logistic_partner__name"],
            row["status"],
        ])
