import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/pincodeserviceability"

payload = {
    "source_Pincode": "560100",
    "destination_Pincode": "201301"
}

response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
