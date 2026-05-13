import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/trackinghistory"

payload = {
    "waybill": "FSPC0004387744"
}

response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
