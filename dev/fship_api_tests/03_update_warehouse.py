import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/updatewarehouse"

payload = {
    "warehouseId": 12142,
    "warehouseName": "QC Bangalore WH",
    "contactName": "Ramesh Kumar",
    "addressLine1": "Electronic City Phase 2",
    "addressLine2": "Near Metro",
    "pincode": "560100",
    "city": "Bangalore",
    "stateId": 29,
    "countryId": 1,
    "phoneNumber": "9876543210",
    "email": "warehouse@company.com"
}

response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
