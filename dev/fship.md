# FShip API – Endpoint-wise Test Files (QC Environment)

**Purpose**
This document contains **endpoint-wise test files** for FShip QC approval.
Each section is written exactly as an **independent test file** with:

* URL
* Method
* Headers
* Sample Payload
* Sample Response

Environment: **QC / Staging**
Base URL: `https://capi-qc.fship.in`

---

## 1. Get Courier List

**URL**
`GET /api/getallcourier`

**Headers**

```json
{
  "Content-Type": "application/json",
  "signature": "<QC_SIGNATURE>"
}
```

**Payload**
*No payload*

**Sample Response**

```json
[
    {
        "courierId": 1,
        "courierName": "Blue dart",
        "logoUrl": "",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 2,
        "courierName": "Xpressbees Surface 500 gm",
        "logoUrl": "",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 9,
        "courierName": "Ekart",
        "logoUrl": "",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 12,
        "courierName": "Ecom Express",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/ecomexpress.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 13,
        "courierName": "Delhivery",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/delhivery.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 14,
        "courierName": "Blue Dart - Express",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/bluedart.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 16,
        "courierName": "DTDC Air",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/dtdc.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 17,
        "courierName": "DTDC Surface",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/dtdc.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 21,
        "courierName": "Delhivery Reverse",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/delhivery.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 33,
        "courierName": "Amazon",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/amazon.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 10045,
        "courierName": "IndiaPost",
        "logoUrl": "https://app-live.fship.in/upload/pro//app-live.fship.in/upload/provider_logo/indiapost.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 10046,
        "courierName": "Shadowfax Reverse",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/shadowfax.jpeg",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 10049,
        "courierName": "Zippyy Express",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/zippyy.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 10050,
        "courierName": "Velocity Express NDD",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/velocityexpress.png",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 10051,
        "courierName": "Ekart NDD",
        "logoUrl": "https://app-live.fship.in/upload/provider_logo/ekart.jpeg",
        "isActive": true,
        "marketType": 0
    },
    {
        "courierId": 10052,
        "courierName": "Xpressbees NDD",
        "logoUrl": "",
        "isActive": true,
        "marketType": 0
    }
]

```

---

## 2. Add Warehouse

**URL**
`POST /api/addwarehouse`

**Headers**

```json
{
  "Content-Type": "application/json",
  "signature": "<QC_SIGNATURE>"
}
```

**Sample Payload**

```json
{
    "warehouseName": "QC Bangalore WH",
    "contactName": "Ramesh Kumar",
    "addressLine1": "Electronic City Phase 1",
    "addressLine2": "Near Infosys",
    "pincode": "560100",
    "city": "Bangalore",
    "phoneNumber": "9876543210",
    "email": "warehouse@company.com"
}
```

**Sample Response**

```json
{
    "warehouseId": 12142,
    "status": true,
    "response": "Warehouse saved successfully.",
    "labelurl": ""
}
```

---

## 3. Update Warehouse

**URL**
`POST /api/updatewarehouse`

**Sample Payload**

```json
{
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
```

**Sample Response**

```json
{
  "warehouseId": 12142,
  "status": true,
  "response": "Warehouse updated successfully"
}
```

---

## 4. Create Forward Order

**URL**
`POST /api/createforwardorder`

**Sample Payload**

```json
{
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
```

**Sample Response**

```json
{
    "route_code": "",
    "order_status": "success",
    "apiorderid": 4387744,
    "waybill": "FSPC0004387744",
    "status": true,
    "response": "Order placed successfully",
    "labelurl": "https://qc-manifest.fship.in/files/label_html/label_FSPC0004387744_4387744_TH.pdf"
}
```

---

## 5. Register Pickup

**URL**
`POST /api/registerpickup`

**Sample Payload**

```json
{
  "waybills": ["FSPC0004387744"]
}
```

**Sample Response**

```json
{
    "apipickuporderids": [
        {
            "pickupOrderId": 196891,
            "waybills": ["FSPC0004387744"],
            "fshipPickupId": "1768807266",
            "courierPickupId": "",
            "pickupDate": "2026-01-20T00:00:00",
            "pickupTime": "11:00:00",
            "serviceProviderId": 9,
            "serviceProviderName": "Ekart",
            "pickupStatusId": 1
        }
    ],
    "status": true,
    "response": "Pickup registered successfully",
    "labelurl": ""
}
```

---

## 6. Shipping Label by Pickup ID

**URL**
`POST /api/shippinglabelbypickupid`

**Sample Payload**

```json
{
  "pickupOrderId": [196891]
}
```

**Sample Response**

```json
{
    "status": "Success",
    "shipmentData": [
        {
            "remark": "Manifest generated.",
            "pickupOrderId": 196891,
            "manifestfile": "https://qc-manifest.fship.in/files/manifest/manifest_196891_1718810708ad4ff7b238d9bf498758f8.pdf",
            "invoicefile": "https://qc-manifest.fship.in/files/invoice/invoice_196891_5ac560b8060b4ba4ad486e5f54eee1db.pdf",
            "labelfile": "https://qc-manifest.fship.in/files/label/label_196891_5980484e4be143698194242b7329940b.pdf"
        }
    ]
}
```

---

## 7. Tracking History

**URL**
`POST /api/trackinghistory`

**Sample Payload**

```json
{
  "waybill": "FSPC0004387744"
}
```

**Sample Response**

```json
{
    "summary": {
        "waybill": "FSPC0004387744",
        "apiorderid": 4387744,
        "orderid": "ORD-QC-001",
        "fulfilledby": "Ekart",
        "statusid": 4,
        "status": "Pickup Initiated",
        "lastscandate": "2026-01-19T12:51:10.01",
        "orderedon": "2026-01-19T00:00:00",
        "expectedDeliveryDate": "2026-01-25T16:30:00"
    },
    "trackingdata": [
        {
            "dateandTime": "2026-01-19T12:51:10.01",
            "status": "Manifested",
            "remark": "Manifested",
            "location": "",
            "shipmentJourney": 1,
            "statusCode": "Manifested",
            "statusCodeType": ""
        },
        {
            "dateandTime": "2026-01-19T12:49:00.373",
            "status": "Booked",
            "remark": "Booked",
            "location": "Bangalore",
            "shipmentJourney": 1,
            "statusCode": "Booked",
            "statusCodeType": ""
        }
    ],
    "status": true,
    "response": "Scan data available.",
    "labelurl": ""
}
```

---

## 8. Shipment Summary

**URL**
`POST /api/shipmentcurrentstatus`

**Sample Payload**

```json
{
  "waybill": "FSPC0004387744"
}
```

**Sample Response**

```json
{
  "summary": {
    "orderId": "ORD-QC-001",
    "waybill": "FSPC0004387744",
    "fullfilledBy": "Ekart",
    "orderedon": "2026-01-19T00:00:00",
    "status": "Pickup Initiated",
    "statusId": 4,
    "remarks": "Manifested",
    "lastScanned": "2026-01-19T12:51:10.01"
  },
  "status": true,
  "response": "Scan data available.",
  "labelurl": ""
}
```

---

## 9. Rate Calculator

**URL**
`POST /api/ratecalculator`

**Sample Payload**

```json
{
    "source_Pincode": "560100",
    "destination_Pincode": "201301",
    "payment_Mode": "COD",
    "amount": 1200,
    "express_Type": "surface",
    "shipment_Weight": 1,
    "shipment_Length": 10,
    "shipment_Width": 10,
    "shipment_Height": 10
}
```

**Sample Response**

```json
{
    "status": true,
    "response": "",
    "shipment_rates": [
        {
            "courier_name": "Amazon",
            "shipping_charge": 83.78,
            "cod_charge": 339.84,
            "rto_charge": 60.18,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 33,
            "expectedDeliveryDate": "2026-01-26T13:00:37"
        },
        {
            "courier_name": "Blue dart",
            "shipping_charge": 31.86,
            "cod_charge": 28.32,
            "rto_charge": 8.26,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 1,
            "expectedDeliveryDate": "2026-01-22T13:00:37"
        },
        {
            "courier_name": "Blue Dart - Express",
            "shipping_charge": 60.18,
            "cod_charge": 198.24,
            "rto_charge": 36.58,
            "service_mode": "air",
            "zone_name": "Roi",
            "courier_id": 14,
            "expectedDeliveryDate": "2026-01-24T13:00:37"
        },
        {
            "courier_name": "Delhivery",
            "shipping_charge": 55.46,
            "cod_charge": 169.92,
            "rto_charge": 31.86,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 13,
            "expectedDeliveryDate": "2026-01-26T13:00:37"
        },
        {
            "courier_name": "DTDC Air",
            "shipping_charge": 69.62,
            "cod_charge": 254.88,
            "rto_charge": 46.02,
            "service_mode": "air",
            "zone_name": "Roi",
            "courier_id": 16,
            "expectedDeliveryDate": "2026-01-24T13:00:37"
        },
        {
            "courier_name": "DTDC Surface",
            "shipping_charge": 74.34,
            "cod_charge": 283.2,
            "rto_charge": 50.74,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 17,
            "expectedDeliveryDate": "2026-01-26T13:00:37"
        },
        {
            "courier_name": "Ecom Express",
            "shipping_charge": 50.74,
            "cod_charge": 141.6,
            "rto_charge": 27.14,
            "service_mode": "air",
            "zone_name": "Roi",
            "courier_id": 12,
            "expectedDeliveryDate": "2026-01-24T13:00:37"
        },
        {
            "courier_name": "Ekart",
            "shipping_charge": 46.02,
            "cod_charge": 113.28,
            "rto_charge": 22.42,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 9,
            "expectedDeliveryDate": "2026-01-26T13:00:37"
        },
        {
            "courier_name": "Ekart NDD",
            "shipping_charge": 107.38,
            "cod_charge": 481.44,
            "rto_charge": 83.78,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 10051,
            "expectedDeliveryDate": "2026-01-21T13:00:37"
        },
        {
            "courier_name": "IndiaPost",
            "shipping_charge": 93.22,
            "cod_charge": 396.48,
            "rto_charge": 69.62,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 10045,
            "expectedDeliveryDate": "2026-01-26T13:00:37"
        },
        {
            "courier_name": "Velocity Express NDD",
            "shipping_charge": 102.66,
            "cod_charge": 453.12,
            "rto_charge": 79.06,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 10050,
            "expectedDeliveryDate": "2026-01-21T13:00:37"
        },
        {
            "courier_name": "Xpressbees NDD",
            "shipping_charge": 112.1,
            "cod_charge": 509.76,
            "rto_charge": 88.5,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 10052,
            "expectedDeliveryDate": "2026-01-21T13:00:37"
        },
        {
            "courier_name": "Xpressbees Surface 500 gm",
            "shipping_charge": 36.58,
            "cod_charge": 56.64,
            "rto_charge": 12.98,
            "service_mode": "surface",
            "zone_name": "Roi",
            "courier_id": 2,
            "expectedDeliveryDate": "2026-01-26T13:00:37"
        },
        {
            "courier_name": "Zippyy Express",
            "shipping_charge": 112.1,
            "cod_charge": 509.76,
            "rto_charge": 88.5,
            "service_mode": "air",
            "zone_name": "Roi",
            "courier_id": 10049,
            "expectedDeliveryDate": "2026-01-24T13:00:37"
        }
    ]
}
```

---

## 10. Pincode Serviceability

**URL**
`POST /api/pincodeserviceability`

**Sample Payload**

```json
{
    "source_Pincode": "560100",
    "destination_Pincode": "201301"
}
```

**Sample Response**

```json
{
    "source": "Bangalore, Karnataka",
    "destination": "Gautam Buddha Nagar, Uttar Pradesh",
    "source_pincode": "560100",
    "destination_pincode": "201301",
    "zone": "Roi",
    "pickup": "Yes",
    "delivery": "Yes",
    "cod": "Yes",
    "status": true,
    "response": "Valid and servicable pincodes.",
    "labelurl": ""
}
```

---

## 11. Create Reverse Order

**URL**
`POST /api/createreverseorder`

**Sample Payload**

```json
{
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
            "isFragileProduct": false,
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
    "isQcRequired": false,
    "courierId": 21,
    "isTaxIncluded": false,
}
```

**Sample Response**

```json
{
    "route_code": "",
    "order_status": "success",
    "apiorderid": 4388227,
    "waybill": "6106510210873",
    "status": true,
    "response": "Order placed successfully",
    "labelurl": ""
}
```
