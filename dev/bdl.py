import requests

url = "https://api.boxdlogistics.com/seller/v1/warehouse/create/"

headers = {
    "Authorization": "Token 4a3f6394b11922cc575e2bd4ddf79629ef45013dc53d2cd9dc3ffcd2fad5a59b",
    "Content-Type": "application/json"
}

payload = {
    "name": "Delhi Warehouse",
    "address": "Okhla Phase 2",
    "city": "Delhi",
    "state": "Delhi",
    "pincode": "110020",
    "phone": "9999999999",
    "email": "warehouse@test.com"
}

response = requests.post(
    url,
    json=payload,
    headers=headers,
    timeout=30
)

print(response.status_code)
print(response.json())