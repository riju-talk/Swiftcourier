import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/addwarehouse"

payload = {
    "warehouseName": "QC Bangalore WH",
    "contactName": "Ramesh Kumar",
    "addressLine1": "Electronic City Phase 1",
    "addressLine2": "Near Infosys",
    "pincode": "560100",
    "city": "Bangalore",
    "phoneNumber": "9876543210",
    "email": "warehouse@company.com"
}

response = requests.post(url, json=payload, headers=HEADERS)

print
print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
