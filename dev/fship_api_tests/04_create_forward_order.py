import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/createforwardorder"

payload = {
    "customer_Name": "Amit Sharma",
    "customer_Mobile": "9999999999",
    "customer_Emailid": "amit@gmail.com",
    "customer_Address": "Sector 62",
    "landMark": "Near Metro",
    "customer_Address_Type": "Home",
    "customer_PinCode": "201301",
    "customer_City": "Noida",
    "orderId": "ORD-QC-001",
    "invoice_Number": "INV-QC-001",
    "payment_Mode": 1,
    "express_Type": "surface",
    "order_Amount": 1200,
    "tax_Amount": 0,
    "extra_Charges": 0,
    "total_Amount": 1200,
    "cod_Amount": 1200,
    "shipment_Weight": 1,
    "shipment_Length": 10,
    "shipment_Width": 10,
    "shipment_Height": 10,
    "pick_Address_ID": 12142,
    "products": [
        {
            "productName": "T-Shirt",
            "unitPrice": 1200,
            "quantity": 1,
            "sku": "TSHIRT001"
        }
    ],
    "courierId": 9
}

response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.text)
