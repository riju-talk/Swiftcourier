from collections import defaultdict
from datetime import datetime

import pytz
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.timezone import now

# ----------------------------------
# Timezone (IST)
# ----------------------------------
IST = pytz.timezone("Asia/Kolkata")

# ----------------------------------
# Date range (IST aware)
# ----------------------------------
start_date = IST.localize(datetime(2026, 5, 12))
end_date = IST.localize(datetime(2026, 5, 20))

# ----------------------------------
# Step 1 → Summary
# ----------------------------------
summary = (
    Order.objects.filter(
        shipment__booked_at__gte=start_date,
        shipment__booked_at__lt=now(),
        # shipment__booked_at__lt=end_date,
    )
    .exclude(status__in=["cancelled", "ready_to_ship"])
    .annotate(o_date=TruncDate("shipment__booked_at", tzinfo=IST))
    .values(
        "o_date",
        "user_id",
        "user__full_name",
        "user__company_name",
        "user__email",
    )
    .annotate(total_orders=Count("id"))
    .order_by("o_date", "user__full_name")
)

# ----------------------------------
# Step 2 → Fetch AWBs
# ----------------------------------
awb_map = defaultdict(list)

awb_rows = (
    Order.objects.filter(
        shipment__booked_at__gte=start_date,
        shipment__booked_at__lte=now(),
    )
    .exclude(status__in=["cancelled", "ready_to_ship"])
    .annotate(o_date=TruncDate("shipment__booked_at", tzinfo=IST))
    .values(
        "o_date",
        "user_id",
        "awb_number",
        "status",
        "logistic_partner__name",
        "shipment__booked_at",
    )
)

for row in awb_rows.iterator():
    if not row["awb_number"]:
        continue
    booked_at = row["shipment__booked_at"]
    if timezone.is_aware(booked_at):
        booked_at = booked_at.astimezone(IST)
    else:
        booked_at = IST.localize(booked_at)
    key = (row["o_date"], row["user_id"])
    awb_map[key].append(
        (
            row["awb_number"],
            row["status"],
            row["logistic_partner__name"],
            booked_at.date(),
            booked_at.time(),
        )
    )

# ----------------------------------
# Step 3 → Fetch Users
# ----------------------------------
user_ids = {row["user_id"] for row in summary}
users = User.objects.filter(id__in=user_ids)
user_map = {user.id: user for user in users}

# ----------------------------------
# Step 4 → Print comma-separated output
# ----------------------------------
header = [
    "Order Date",
    "Total Orders",
    "User Name",
    "Company Name",
    "User ID",
    "Email",
    "AWB Number",
    "Status",
    "Courier",
    "Booked Date (IST)",
    "Booked Time (IST)",
]

print(",".join(header))

for row in summary.iterator():
    user = user_map.get(row["user_id"])
    key = (row["o_date"], row["user_id"])
    awbs = awb_map.get(key, [("", "", "", "", "")])
    for awb in awbs:
        line = [
            str(row["o_date"]),
            str(row["total_orders"]),
            row["user__full_name"] or "",
            row["user__company_name"] or "",
            user.shipzee_code if user else "",
            row["user__email"],
            str(awb[0]),
            str(awb[1]),
            str(awb[2]),
            str(awb[3]),
            str(awb[4]),
        ]
        print(",".join(line))
