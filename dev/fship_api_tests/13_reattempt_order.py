import requests
from fship_integration.config import BASE_URL, HEADERS
from datetime import datetime

url = f"{BASE_URL}/api/reattemptorder"

payload = {
    "apiorderid": 56789,
    "action": "re-attempt",
    "reattempt_date": datetime.utcnow().isoformat(),
    "contact_name": "Amit Sharma",
    "complete_address": "Sector 62, Noida",
    "mobilenumber": "9999999999",
    "remarks": "Customer requested reattempt"
}

response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
