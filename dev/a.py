# import csv


# o = Order.objects.exclude(status__in=["pending_pickup", "cancelled"]).filter(logistic_partner__abbreviation__startswith="pd_")

# with open("test.csv", "w") as f:
#     w = csv.writer(f)
#     w.writerow([
#         "IdiotShip Id",
#         "AWB Number",
#         "User's Name",
#         "User's Email",
#         "Order Created At",
#         "Order Booked At",
#         "Courier Partner",
#     ])
#     for i in o:
#         w.writerow(
#             [
#                 i.id,
#                 i.awb_number,
#                 i.user.full_name,
#                 i.user.email,
#                 i.created_at,
#                 i.shipment.booked_at,
#                 i.logistic_partner.name,
#             ]
#         )

# import csv

# u = User.objects.filter(is_active=True, role=User.USER)

# with open("test.csv", "w") as f:
#     w = csv.writer(f)

#     w.writerow([
#         "IdiotShip User ID",
#         "Full Name",
#         "Email Id",
#         "Mobile No",
#         "Company Name",
#     ])
#     for i in u:
#         w.writerow([
#             i.id,
#             i.full_name,
#             i.email,
#             i.contact_no,
#             i.company_name,
#         ])
# from collections import defaultdict
# import csv


# cod_rem = CODRemittance.objects.filter(_status="paid")
# data = defaultdict(list)

# for i in cod_rem:
#     data[i._user.shipzee_code].append(i)


# with open("cod_remittance.csv", "w") as f:
#     w = csv.writer(f)
#     w.writerow(["User Code","User Email","User Name","Payout Date","Generated COD","Freight Deduction","Early COD Charges Percnt","Early COD Charges","COD Reverse","Remittance Amount","COD File","Amount Paid","Order Count","Remark"])
#     print(data)
#     for user_code, cods in data.items():
#         print(user_code, cods)
#         for m in cods:
#             w.writerow([user_code,m._user.email,m._user.full_name,m._payout_date,m._generated_cod,m._freight_deduction,m._early_cod_charge_percentage,m._early_cod_charge,m._remittance_amount,"https://app.idiotship.tech" + m._file.url if m._file else "N/A",m._amount_paid,m._order_count,m._remarks])

# orders = Order.objects.filter(user__email="princarathi@gmail.com").exclude(
#     status__in=["cancelled", "ready_to_ship", "processing"]
# )
# for o in orders:
#     shipment = order.shipment
#     vol_weight = shipment.
""" """


