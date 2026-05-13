import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/shippinglabelbypickupid"

payload = {
    "pickupOrderId": [196891]
}

response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
