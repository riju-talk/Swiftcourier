import csv
from datetime import datetime
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.timezone import now
from django.contrib.auth import get_user_model

User = get_user_model()

# ----------------------------------
# Date range
# ----------------------------------
start_date = timezone.make_aware(datetime(2026, 5, 1))

# ----------------------------------
# Main query (ONLY DB fields)
# ----------------------------------
summary = (
    Order.objects.filter(
        shipment__booked_at__gte=start_date,
        shipment__booked_at__lte=now(),
    )
    .exclude(status__in=["cancelled", "ready_to_ship"])
    .annotate(o_date=TruncDate("shipment__booked_at"))
    .values(
        "o_date",
        "user_id",
        "user__full_name",
        "user__company_name",
    )
    .annotate(total_orders=Count("id"))
    .order_by("o_date", "user__full_name")
)

# ----------------------------------
# Fetch users in ONE query
# ----------------------------------
user_ids = {row["user_id"] for row in summary}

users = User.objects.filter(id__in=user_ids)
user_map = {user.id: user for user in users}

# ----------------------------------
# Output
# ----------------------------------

print("Order Date", "Total Orders", "User Name", "Company Name", "User ID", sep=",")
for row in summary:
    user = user_map.get(row["user_id"])
    print(
        row["o_date"],
        row["total_orders"],
        row["user__full_name"],
        row["user__company_name"],
        user.shipzee_code if user else "",
        sep=",",
    )

# from collections import defaultdict
# from datetime import datetime

# import pytz
# from openpyxl import Workbook

# from django.db.models import Count
# from django.db.models.functions import TruncDate
# from django.utils import timezone
# from django.utils.timezone import now

# # ----------------------------------
# # Timezone (IST)
# # ----------------------------------
# IST = pytz.timezone("Asia/Kolkata")

# # ----------------------------------
# # Date range (IST aware)
# # ----------------------------------
# start_date = IST.localize(datetime(2026, 1, 1))

# # ----------------------------------
# # Excel Workbook
# # ----------------------------------
# wb = Workbook()
# ws = wb.active
# ws.title = "Orders"

# header = [
#     "Order Date",
#     "Total Orders",
#     "User Name",
#     "Company Name",
#     "User ID",
#     "AWB Number",
#     "Status",
#     "Courier",
#     "Booked Date (IST)",
#     "Booked Time (IST)",
# ]

# ws.append(header)

# # ----------------------------------
# # Step 1 → Summary
# # ----------------------------------
# summary = (
#     Order.objects.filter(
#         shipment__booked_at__gte=start_date,
#         shipment__booked_at__lte=now(),
#     )
#     .exclude(status__in=["cancelled", "ready_to_ship"])
#     .annotate(o_date=TruncDate("shipment__booked_at", tzinfo=IST))
#     .values(
#         "o_date",
#         "user_id",
#         "user__full_name",
#         "user__company_name",
#     )
#     .annotate(total_orders=Count("id"))
#     .order_by("o_date", "user__full_name")
# )

# # ----------------------------------
# # Step 2 → Fetch AWBs
# # ----------------------------------
# awb_map = defaultdict(list)

# awb_rows = (
#     Order.objects.filter(
#         shipment__booked_at__gte=start_date,
#         shipment__booked_at__lte=now(),
#     )
#     .exclude(status__in=["cancelled", "ready_to_ship"])
#     .annotate(o_date=TruncDate("shipment__booked_at", tzinfo=IST))
#     .values(
#         "o_date",
#         "user_id",
#         "awb_number",
#         "status",
#         "logistic_partner__name",
#         "shipment__booked_at",
#     )
# )

# for row in awb_rows.iterator():
#     if not row["awb_number"]:
#         continue
#     booked_at = row["shipment__booked_at"]
#     if timezone.is_aware(booked_at):
#         booked_at = booked_at.astimezone(IST)
#     else:
#         booked_at = IST.localize(booked_at)
#     key = (row["o_date"], row["user_id"])
#     awb_map[key].append(
#         (
#             row["awb_number"],
#             row["status"],
#             row["logistic_partner__name"],
#             booked_at.date(),
#             booked_at.time(),
#         )
#     )

# # ----------------------------------
# # Step 3 → Fetch Users
# # ----------------------------------
# user_ids = {row["user_id"] for row in summary}
# users = User.objects.filter(id__in=user_ids)
# user_map = {user.id: user for user in users}

# # ----------------------------------
# # Step 4 → Write rows to Excel
# # ----------------------------------
# for row in summary.iterator():
#     user = user_map.get(row["user_id"])
#     key = (row["o_date"], row["user_id"])
#     awbs = awb_map.get(key, [("", "", "", "", "")])
#     for awb in awbs:
#         ws.append(
#             [
#                 str(row["o_date"]),
#                 row["total_orders"],
#                 row["user__full_name"] or "",
#                 row["user__company_name"] or "",
#                 user.shipzee_code if user else "",
#                 awb[0],
#                 awb[1],
#                 awb[2],
#                 awb[3],
#                 awb[4],
#             ]
#         )

# # ----------------------------------
# # Save Excel
# # ----------------------------------
# file_path = "orders_report1.xlsx"
# wb.save(file_path)

# print(f"Excel file saved: {file_path}")
