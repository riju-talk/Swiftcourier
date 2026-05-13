# import requests


# url = "https://backend.fulfillzy.com/authToken"  # replace with your actual URL

# data = {"username": "bluedart500gm@atomaicmail.io", "password": "Admin@123"}

# headers = {"Content-Type": "application/json", "Accept": "application/json"}
# response = requests.post(url, json=data, headers=headers)

# print("Status Code:", response.status_code)
# print("Response Text:")
# print(response.text)


# response :
#  eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzYwMzM1OTc1LCJqdGkiOiJlODJjM2U0MmU2NGU0ZjA1YWU4YzAzYzM4YjU2NzM3YiIsInVzZXJfaWQiOjU2fQ.Zc-iwJKdVoexOB7pa33a84j4TYdjphZtOFJInzi4PAQ


# test 2 order creation

# url = "https://backend-uat.fulfillzy.com/order_allocation/api/allocate_waybill"

# data = {
#     "source": "api",
#     "returnShipmentFlag": False,
#     "Shipment": {
#         "code": "RATEDANE",
#         "orderCode": "307066",
#         "saleOrderCode": "",
#         "invoiceCode": "KRTI/24-25/59092",
#         "orderDate": "17-Dec-2024 21:55:42",
#         "weight": "1230.0",
#         "length": "110.0",
#         "height": "115.0",
#         "breadth": "110.0",
#         "items": [
#             {
#                 "name": "Black Bell Bottom 4-Way Stretch Pants",
#                 "description": "Black Bell Stretch Pants",
#                 "quantity": 1,
#                 "skuCode": "SFPANT50438L",
#                 "itemPrice": 618.45,
#                 "hsnCode": "61046300",
#             }
#         ],
#     },
#     "deliveryAddressDetails": {
#         "name": "Jitender",
#         "email": "",
#         "phone": "7906251733",
#         "address1": "House no. 108",
#         "address2": "",
#         "pincode": "160018",
#         "city": "CHANDIGARH",
#         "state": "Chandigarh",
#         "country": "India",
#         "gstin": "",
#     },
#     "pickupAddressDetails": {
#         "name": "RETAIL PRIVATE LIMITED",
#         "email": "",
#         "phone": "9999999999",
#         "address1": "Khasra",
#         "address2": "17/3",
#         "pincode": "122001",
#         "city": "Gurgaon",
#         "state": "Haryana",
#         "country": "India",
#         "gstin": "",
#     },
#     "returnAddressDetails": {
#         "name": "RETAIL PRIVATE LIMITED",
#         "email": "",
#         "phone": "9999999999",
#         "address1": "Khasra",
#         "address2": "17/3",
#         "pincode": "122001",
#         "city": "Gurgaon",
#         "state": "Haryana",
#         "country": "India",
#         "gstin": "",
#     },
#     "currencyCode": "INR",
#     "paymentMode": "PREPAID",
#     "totalAmount": "618.45",
#     "collectableAmount": "0",
# }


# headers = {
#     "Content-Type": "application/json",
#     "Authorization": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzYwMzM2NTcyLCJqdGkiOiJmZmRmMmRkYWJhZTE0OTAyODVkMzM1ZjU5OWUwYjIyYSIsInVzZXJfaWQiOjU2fQ.aoLrmf9OWlCmTbIrG4FXX_EyvRKL5IRTDBhZV-hRb9s",
# }


# response = requests.post(url, json=data, headers=headers)

# print("Status Code:", response.status_code)
# print("Response Text:")
# print(response.text)


# response :

#  Status Code: 200
# Response Text:
# {"status":"SUCCESS","waybill":"PRD000737200P","courierName":"Cuberoote","shippingLabel":"https://backend-uat.fulfillzy.com/api/order/label/PRD000737200P.pdf","routeCode":"Chandigarh"}


# test 3 order cancelation

# url = "https://backend-uat.fulfillzy.com/cancel"


# data = {
#     "waybill": "PRD000737200P",
# }

# headers = {
#     "Content-Type": "application/json",
#     "Authorization": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzYwMzM2NTcyLCJqdGkiOiJmZmRmMmRkYWJhZTE0OTAyODVkMzM1ZjU5OWUwYjIyYSIsInVzZXJfaWQiOjU2fQ.aoLrmf9OWlCmTbIrG4FXX_EyvRKL5IRTDBhZV-hRb9s",
# }

# response = requests.post(url, json=data, headers=headers)


# print("Status Code:", response.status_code)
# print("Response Text:")
# print(response.text)


# response :

# Status Code: 200
# Response Text:
# {"waybill":"PRD000737200P","status":"SUCCESS","errorMessage":"Cancelled successfully."}

import requests

url = "https://api.jiffy.world/warehouses"

payload = "{\n  \"name\": \"Test Warehouse 2\",\n  \"person_name\": \"John Doe\",\n  \"phone\": \"9876543210\",\n  \"email\": \"john@example.com\",\n  \"address_1\": \"123 Business Street, Industrial Area\",\n  \"address_2\": \"Near Metro Station\",\n  \"city\": \"Delhi\",\n  \"state\": \"Delhi\",\n  \"country\": \"India\",\n  \"pincode\": \"110001\",\n  \"gst_number\": \"27ABCDE1234F1Z5\"\n}"
headers = {}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
