# import requests

# url = "https://api.rapidshyp.com/rapidshyp/apis/v1/serviceabilty_check"

# headers = {
#     "rapidshyp-token": "abac757e593a5ebd8d4ad5bacedcb28c188cdc2c1a8ccb61f7b07452477fae0e",
#     "Content-Type": "application/json",
# }

# payload = {
#     "Pickup_pincode": "110075",
#     "Delivery_pincode": "110075",
#     "cod": False,
#     "total_order_value": 2000,
#     "weight": 0.5,
# }

# response = requests.post(url, json=payload, headers=headers)

# print("Status Code:", response.status_code)
# print("Response:", response.text)

# d = response.json().get("serviceable_courier_list", [])

# print("-" * 40)

# for courier in d:
#     print("Courier Name:", courier.get("courier_name"))
#     print("Courier Code:", courier.get("courier_code"))
#     print("-" * 40)

# import http.client
# import json

# conn = http.client.HTTPSConnection("nd8ggj.api.infobip.com")
# payload = json.dumps(
#     {
#         "messages": [
#             {
#                 "from": "447860089411",
#                 "to": "918929892907",
#                 "messageId": "62bf63c0-2b9a-492c-ba51-02890b4e1550",
#                 "content": {
#                     "templateName": "test_whatsapp_template_en",
#                     "templateData": {"body": {"placeholders": ["Idiotship"]}},
#                     "language": "en",
#                 },
#             }
#         ]
#     }
# )
# headers = {
#     "Authorization": "App 1f621488515eb4d602aeb1bfdd41a929-db25d353-5545-4e42-a07a-0cf56164ae2c",
#     "Content-Type": "application/json",
#     "Accept": "application/json",
# }
# conn.request("POST", "/whatsapp/1/message/template", payload, headers)
# res = conn.getresponse()
# data = res.read()
# print(data.decode("utf-8"))

# ------------------------------------------
# from django.utils.timezone import now, make_aware
# import datetime

# data = {
#     "23814": "I77444275",
#     "23812": "I77444389",
#     "23810": "I77444415",
#     "23808": "I77444392",
#     "23803": "I77444403",
#     "23802": "I77444424",
#     "23801": "I77444418",
#     "23798": "I77444419",
#     "23797": "I77444386",
#     "23795": "I77444416",
#     "23794": "I77444388",
#     "23793": "I77444379",
#     "23792": "I77444421",
#     "23791": "I77444381",
#     "23789": "I77444385",
#     "23785": "I77444405",
#     "23784": "I77444380",
#     "23780": "I77444399",
#     "23776": "I77444400",
#     "23774": "I77444409",
#     "23769": "I77444393",
#     "23765": "I77444404",
#     "23764": "I77444391",
#     "23763": "I77444390",
#     "23760": "I77444425",
#     "23759": "I77444406",
#     "23754": "I77444420",
#     "23750": "I77444396",
#     "23748": "I77444395",
#     "23747": "I77444394",
#     "23745": "I77444414",
#     "23740": "I77444422",
#     "23735": "I77444411",
#     "23730": "I77444387",
#     "23729": "I77444407",
#     "23719": "I77444417",
#     "23718": "I77444397",
#     "23711": "I77444382",
#     "23705": "I77444383",
#     "23702": "I77444412",
#     "23700": "I77444402",
#     "23695": "I77444401",
#     "23691": "I77444423",
#     "23690": "I77444398",
#     "23686": "I77444384",
#     "23684": "I77444413",
#     "23683": "I77444408",
#     "23681": "I77444410",
# }

# orders = Order.objects.filter(id__in=data.keys())
# for o in orders:
#     o.shipment.booked_at = make_aware(datetime.datetime(2026, 11, 3, 16, 0, 0))
#     o.shipment.save()

# -------------------------------------------
# from django.utils import timezone
# import uuid

# awb_numbers = []

# orders = Order.objects.filter(awb_number__in=awb_numbers)
# user = User.objects.get(email="email.rohitjobmbd@gmail.com")

# for o in orders:
#     o.update_status("ready_to_ship")
#     tr = Transaction.create_transaction(
#         user=user,
#         merchant_txn_id=str(o.id) + "_cancel_" + str(uuid.uuid4()),
#         amount_rs=90.86,
#         desc="cancelled_order",
#         transaction_type="credit",
#     )
#     tr.credit(awb_number=o.awb_number)
#     o.cancel_data[str(o.awb_number)] = {
#         "cancelled_at": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
#         "courier": (
#             f"{o.logistic_partner.name} ({o.logistic_partner.abbreviation})"
#             if o.logistic_partner
#             else "N/A"
#         ),
#         "refund_amount": o.payment.amount,
#     }
#     o.save()

data = {
    "77672834816": ["jf_bd_500", "cancelled"],
    "76795348722": ["jf_bd_500", "cancelled"],
    "76795348733": ["jf_bd_500", "cancelled"],
    "76794203043": ["jf_bd_500", "cancelled"],
    "76794203091": ["jf_bd_500", "cancelled"],
    "76794203146": ["jf_bd_500", "cancelled"],
    "76794118483": ["jf_bd_500", "cancelled"],
    "76794118531": ["jf_bd_500", "cancelled"],
    "76794118612": ["jf_bd_500", "cancelled"],
    "76794118645": ["jf_bd_500", "cancelled"],
    "76792960580": ["jf_bd_500", "cancelled"],
    "76792334010": ["jf_bd_500", "cancelled"],
    "77654425026": ["jf_bd_500", "cancelled"],
    "77654425063": ["jf_bd_500", "cancelled"],
    "45946710343066": ["jf_dv_500", "cancelled"],
    "45946710343070": ["jf_dv_500", "cancelled"],
    "45946710343081": ["jf_dv_500", "cancelled"],
    "45946710343092": ["jf_dv_500", "cancelled"],
    "45946710343103": ["jf_dv_500", "cancelled"],
    "45946710343114": ["jf_dv_500", "cancelled"],
    "45946710343125": ["jf_dv_500", "cancelled"],
    "45946710343136": ["jf_dv_500", "cancelled"],
    "45946710343140": ["jf_dv_500", "cancelled"],
    "45946710343151": ["jf_dv_500", "cancelled"],
    "45946710343162": ["jf_dv_500", "cancelled"],
    "45946710343173": ["jf_dv_500", "cancelled"],
    "45946710343184": ["jf_dv_500", "cancelled"],
    "45946710343195": ["jf_dv_500", "cancelled"],
    "45946710343206": ["jf_dv_500", "cancelled"],
    "SF3129690883JIY": ["jf_sf_500", "cancelled"],
    "45946713515256": ["jf_dv_500", "delivered"],
    "45946713515271": ["jf_dv_500", "delivered"],
}

orders = Order.objects.filter(awb_number__in=data.keys())
for o in orders:
    d = data[o.awb_number]
    o.logistic_partner = Courier.objects.get(abbreviation=d[0])
    o.save()
    o.update_status(new_status=d[1])