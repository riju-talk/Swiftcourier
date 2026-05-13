import requests
from fship_integration.config import BASE_URL, HEADERS

url = f"{BASE_URL}/api/createreverseorder"

payload = {
    "customer_Name": "Amit Kumar",
    "customer_Mobile": "9876543210",
    "customer_Emailid": "amit.kumar@testmail.com",
    "customer_Address": "Flat 402, Sector 22",
    "landMark": "Near Metro Station",
    "customer_Address_Type": "Home",
    "customer_PinCode": "110074",
    "customer_City": "New Delhi",
    "orderId": "REV-ORD-1001",
    "invoice_Number": "INV-REV-1001",
    "order_Amount": 1499,
    "tax_Amount": 0,
    "extra_Charges": 0,
    "total_Amount": 1499,
    "pickUpAddressId": 12142,
    "shipment_Weight": 1,
    "shipment_Length": 25,
    "shipment_Width": 20,
    "shipment_Height": 10,
    "volumetric_Weight": 1,
    "products": [
        {
            "productId": "PROD-TS-001",
            "productName": "Men Cotton T-Shirt",
            "quantity": 1,
            "unitPrice": 1499,
            "productCategory": "Apparel",
            "sku": "TSHIRT-BLK-L",
            "hsnCode": "610910",
            "taxRate": 0,
            "productDiscount": 0,
            "brandName": "Nike",
            "color": "Black",
            "size": "L",
            "eanNo": "8901234567890",
            "serialNo": "",
            "imei": "",
            "isFragileProduct": False,
            "productImageUrl": "https://example.com/images/tshirt.jpg",
            "returnType": 0,
            "returnReason": "Size issue",
            "qcParameters": [
                {
                    "questionId": "Take_Picture",
                    "question": "Take a Picture of the Item you are collecting",
                    "value": "No",
                },
                {
                    "questionId": "Check_Usage",
                    "question": "Has the product been used?",
                    "value": "No",
                },
                {
                    "questionId": "Check_Colour",
                    "question": "Is the color matching the listing?",
                    "value": "No",
                },
            ],
        }
    ],
    "isQcRequired": False,
    "courierId": 21,
    "isTaxIncluded": False,
}


response = requests.post(url, json=payload, headers=HEADERS)

print("STATUS:", response.status_code)
print("RESPONSE:", response.text)
