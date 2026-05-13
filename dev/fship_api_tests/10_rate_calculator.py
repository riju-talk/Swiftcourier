import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/ratecalculator"

payload = {
    "source_Pincode": "560100",
    "destination_Pincode": "201301",
    "payment_Mode": "COD",
    "amount": 1200,
    "express_Type": "surface",
    "shipment_Weight": 1,
    "shipment_Length": 10,
    "shipment_Width": 10,
    "shipment_Height": 10
}

response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
