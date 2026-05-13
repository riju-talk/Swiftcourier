from collections import defaultdict
from datetime import datetime

import pytz
import pandas as pd
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
end_date = IST.localize(datetime(2026, 5, 15))

# ----------------------------------
# Step 1 → Summary
# ----------------------------------
summary = (
    Order.objects.filter(
        shipment__booked_at__gte=start_date,
        shipment__booked_at__lt=end_date,
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
        shipment__booked_at__lt=end_date,
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
            booked_at.strftime("%Y-%m-%d"),
            booked_at.strftime("%H:%M:%S"),
        )
    )

# ----------------------------------
# Step 3 → Fetch Users
# ----------------------------------
user_ids = {row["user_id"] for row in summary}
users = User.objects.filter(id__in=user_ids)
user_map = {user.id: user for user in users}

# ----------------------------------
# Step 4 → Build Data Rows
# ----------------------------------
rows = []

for row in summary.iterator():
    user = user_map.get(row["user_id"])
    key = (row["o_date"], row["user_id"])
    awbs = awb_map.get(key, [("", "", "", "", "")])
    for awb in awbs:
        rows.append(
            {
                "Order Date": row["o_date"],
                "Total Orders": row["total_orders"],
                "User Name": row["user__full_name"] or "",
                "Company Name": row["user__company_name"] or "",
                "User ID": user.shipzee_code if user else "",
                "Email": row["user__email"] or "",
                "AWB Number": awb[0],
                "Status": awb[1],
                "Courier": awb[2],
                "Booked Date (IST)": awb[3],
                "Booked Time (IST)": awb[4],
            }
        )

# ----------------------------------
# Step 5 → Export to Excel
# ----------------------------------
df = pd.DataFrame(rows)

file_name = (
    f"order_report_"
    f"{start_date.strftime('%Y%m%d')}_"
    f"to_"
    f"{(end_date - timezone.timedelta(days=1)).strftime('%Y%m%d')}.xlsx"
)

df.to_excel(file_name, index=False)

print(f"Excel file created successfully: {file_name}")
print(f"Total rows exported: {len(df)}")
