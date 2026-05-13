import requests
# from fship_api_tests.config import BASE_URL, HEADERS

BASE_URL = "https://capi.fship.in"

SIGNATURE = "58408e83c2421ab2991feba103a4fdff2a07486325577899b48577394b70a4d8"

HEADERS = {"Content-Type": "application/json", "signature": SIGNATURE}

url = f"{BASE_URL}/api/getallcourier"

response = requests.get(url, headers=HEADERS)


print("URL:", url)
print("STATUS:", response.status_code)
print("RESPONSE:", response.json())
