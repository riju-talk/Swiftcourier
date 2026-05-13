# IdiotShip API Documentation

> **Version:** 1.0  
> **Base URL:** `https://api.idiotship.tech/v1`  
> **Content-Type:** `application/json`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Users](#users)
3. [Shipments / Orders](#shipments--orders)
4. [Couriers](#couriers)
5. [Rate & Serviceability](#rate--serviceability)
6. [NDR (Non-Delivery Report)](#ndr-non-delivery-report)
7. [COD Remittance](#cod-remittance)
8. [Wallet & Transactions](#wallet--transactions)
9. [Hubs (Pickup Addresses)](#hubs-pickup-addresses)
10. [Response Conventions](#response-conventions)
11. [Error Codes](#error-codes)

---

## Authentication

IdiotShip uses **Bearer Token** authentication. All endpoints (except login) require the token in the `Authorization` header.

```
Authorization: Bearer <token>
```

Tokens are obtained via the login endpoint and must be included in every subsequent request.

---

## Users

### POST Generate Auth Token (Login)

```
POST /v1/users/login
```

Use this endpoint to authenticate and receive a Bearer token.

**Headers**

| Key          | Value            |
|--------------|------------------|
| Content-Type | application/json |

**Body**

```json
{
  "email": "merchant@example.com",
  "password": "yourpassword"
}
```

**Parameters**

| Field    | Required | Type   | Description              |
|----------|----------|--------|--------------------------|
| email    | Yes      | string | Registered email address |
| password | Yes      | string | Account password         |

**Response — Success**

```json
{
  "status": true,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id": 1,
      "email": "merchant@example.com",
      "full_name": "Rahul Sharma",
      "company_name": "My Store Pvt Ltd",
      "shipzee_code": "SZC265255",
      "role": "user",
      "balance": 1500.00,
      "contact_no": "9876543210"
    }
  }
}
```

**Response — Failed**

```json
{
  "status": false,
  "message": "Invalid email or password."
}
```

---

## Shipments / Orders

### POST Create Shipment

```
POST /v1/shipments
```

Use this endpoint to create a new shipment and generate an AWB/tracking number.

> **Note:** `order_amount` (selling price of goods) is not auto-calculated. Ensure you send the correct value. Wallet balance will be debited for shipping charges.

**Authorization:** Bearer Token

**Headers**

| Key          | Value            |
|--------------|------------------|
| Content-Type | application/json |

**Parameters**

| Field                        | Required    | Type    | Description / Example                                       |
|------------------------------|-------------|---------|-------------------------------------------------------------|
| order_number                 | Yes         | string  | Your internal order reference. Max 150 chars. e.g. `#1001` |
| payment_type                 | Yes         | string  | Valid values: `prepaid`, `cod`                              |
| order_amount                 | Yes         | float   | Total selling price of goods. e.g. `999.00`                 |
| collectable_amount           | Yes         | float   | For prepaid: `0`.           |
| package_weight               | No          | float   | Weight in kg. e.g. `0.5`                                    |
| package_length               | No          | integer | Package length in cm. e.g. `12`                             |
| package_breadth              | No          | integer | Package breadth in cm. e.g. `12`                            |
| package_height               | No          | integer | Package height in cm. e.g. `12`                             |
| courier_id                   | No          | integer | Specific courier ID. If omitted, auto-selected by preference |
| channel                      | No          | string  | Order source. Values: `shopify`, `amazon`, `woocommerce`, `custom`, `api`. Default: `api` |
| notes                        | No          | string  | Additional instructions                                     |
| consignee[name]              | Yes         | string  | Customer name. Max 200 chars                                |
| consignee[company_name]      | No          | string  | Company name. Max 200 chars                                 |
| consignee[address]           | Yes         | string  | Delivery address line 1. Max 255 chars                      |
| consignee[address_2]         | No          | string  | Delivery address line 2                                     |
| consignee[landmark]          | No          | string  | Nearby landmark                                             |
| consignee[city]              | Yes         | string  | Delivery city                                               |
| consignee[state]             | Yes         | string  | Delivery state                                              |
| consignee[pincode]           | Yes         | string  | 6-digit delivery pincode                                    |
| consignee[phone]             | Yes         | string  | 10-digit customer phone                                     |
| consignee[email]             | No          | string  | Customer email                                              |
| pickup[hub_id]               | Conditional | integer | ID of a saved Hub. Required if pickup address fields not provided |
| pickup[name]                 | Conditional | string  | Pickup contact name                                         |
| pickup[address]              | Conditional | string  | Pickup address line 1                                       |
| pickup[address_2]            | No          | string  | Pickup address line 2                                       |
| pickup[city]                 | Conditional | string  | Pickup city                                                 |
| pickup[state]                | Conditional | string  | Pickup state                                                |
| pickup[pincode]              | Conditional | string  | 6-digit pickup pincode                                      |
| pickup[phone]                | Conditional | string  | 10-digit pickup phone                                       |
| order_items                  | No          | array   | List of items in the order (see below)                      |
| order_items[].name           | No          | string  | Product name                                                |
| order_items[].sku            | No          | string  | Product SKU                                                 |
| order_items[].qty            | No          | integer | Quantity                                                    |
| order_items[].price          | No          | float   | Unit price                                                  |
| order_items[].hsn_code       | No          | string  | HSN code for GST                                            |

**Body Example**

```json
{
  "order_number": "#1001",
  "payment_type": "cod",
  "order_amount": 1200.00,
  "collectable_amount": 1200.00,
  "package_weight": 0.5,
  "package_length": 20,
  "package_breadth": 15,
  "package_height": 10,
  "courier_id": 3,
  "channel": "custom",
  "consignee": {
    "name": "Priya Verma",
    "address": "B-42, Green Park",
    "address_2": "Near Metro Station",
    "landmark": "Opposite Green Park Metro",
    "city": "New Delhi",
    "state": "Delhi",
    "pincode": "110016",
    "phone": "9876543210",
    "email": "priya@example.com"
  },
  "pickup": {
    "hub_id": 5
  },
  "order_items": [
    {
      "name": "Cotton Kurta",
      "sku": "KRT-001",
      "qty": 2,
      "price": 600.00,
      "hsn_code": "62044200"
    }
  ]
}
```

**Response — Success**

```json
{
  "status": true,
  "data": {
    "order_id": "SZ10042",
    "shipment_id": 8821,
    "awb_number": "1100234987654",
    "courier_id": 3,
    "courier_name": "Xpressbees Surface",
    "status": "ready_to_ship",
    "payment_type": "cod",
    "shipping_charges": 52.00,
    "cod_charges": 28.00,
    "total_charges": 80.00,
    "wallet_balance_after": 1420.00
  }
}
```

**Response — Failed (Insufficient Balance)**

```json
{
  "status": false,
  "message": "Insufficient wallet balance. Please recharge to continue."
}
```

**Response — Failed (Blocked Pincode)**

```json
{
  "status": false,
  "message": "Delivery to pincode 110016 is not serviceable."
}
```

**Response — Failed (Validation)**

```json
{
  "status": false,
  "message": "Consignee name is required."
}
```

---

### GET Track Shipment

```
GET /v1/shipments/track/{AWB}
```

Get the full tracking history of a shipment by its AWB number.

**Authorization:** Bearer Token

**URL Parameter**

| Parameter | Description                      |
|-----------|----------------------------------|
| AWB       | AWB / tracking number of shipment |

**Shipment Status Codes**

| Status Code          | Description             |
|----------------------|-------------------------|
| ready_to_ship        | Ready To Ship           |
| processing           | Processing              |
| pending_pickup       | Pending Pickup          |
| in_transit           | In Transit              |
| out_for_delivery     | Out For Delivery        |
| delivered            | Delivered               |
| cancelled            | Cancelled               |
| exception            | Exception               |
| ndr                  | Non-Delivery Report     |
| rto                  | RTO Initiated           |
| rto_in_transit       | RTO In Transit          |
| rto_out_for_delivery | RTO Out For Delivery    |
| rto_delivered        | RTO Delivered           |
| lost                 | Lost                    |
| damaged              | Damaged                 |

**Response — Success**

```json
{
  "status": true,
  "data": {
    "order_id": "SZ10042",
    "order_number": "#1001",
    "awb_number": "1100234987654",
    "courier": "Xpressbees Surface",
    "current_status": "in_transit",
    "payment_type": "cod",
    "booked_at": "2026-05-10T09:00:00Z",
    "shipped_at": "2026-05-11T07:30:00Z",
    "expected_delivery": "2026-05-14",
    "delivered_at": null,
    "consignee": {
      "name": "Priya Verma",
      "city": "New Delhi",
      "state": "Delhi",
      "pincode": "110016"
    },
    "history": [
      {
        "status": "pending_pickup",
        "location": "Gurugram HUB",
        "timestamp": "2026-05-10 09:00:00",
        "description": "Shipment Booked"
      },
      {
        "status": "in_transit",
        "location": "Delhi Gateway (DXN)",
        "timestamp": "2026-05-11 07:30:00",
        "description": "Shipment Arrived at Facility"
      }
    ]
  }
}
```

**Response — Failed**

```json
{
  "status": false,
  "message": "Record not found."
}
```

---

### GET List Orders

```
GET /v1/shipments
```

Returns paginated list of all orders for the authenticated user.

**Authorization:** Bearer Token

**Query Parameters**

| Param    | Required | Description                                                  |
|----------|----------|--------------------------------------------------------------|
| status   | No       | Filter by order status (e.g. `in_transit`, `delivered`)      |
| channel  | No       | Filter by channel (e.g. `shopify`, `custom`)                 |
| page     | No       | Page number. Default: `1`                                    |
| per_page | No       | Records per page. Max: `250`. Default: `50`                  |
| q        | No       | Search by AWB number or order number                         |

**Response — Success**

```json
{
  "status": true,
  "data": {
    "total": 134,
    "page": 1,
    "per_page": 50,
    "orders": [
      {
        "order_id": "SZ10042",
        "order_number": "#1001",
        "awb_number": "1100234987654",
        "courier": "Xpressbees Surface",
        "status": "in_transit",
        "payment_type": "cod",
        "order_amount": 1200.00,
        "shipping_charges": 52.00,
        "channel": "custom",
        "created_at": "2026-05-10T09:00:00Z"
      }
    ]
  }
}
```

---

### POST Cancel Shipment

```
POST /v1/shipments/cancel
```

Cancel a booked shipment. Cancellation is only allowed before pickup.

**Authorization:** Bearer Token

**Body**

```json
{
  "awb": "1100234987654"
}
```

**Parameters**

| Field | Required | Type   | Description        |
|-------|----------|--------|--------------------|
| awb   | Yes      | string | AWB number to cancel |

**Response — Success**

```json
{
  "status": true,
  "message": "Shipment cancelled successfully.",
  "data": {
    "awb_number": "1100234987654",
    "refund_amount": 80.00,
    "cancelled_at": "2026-05-12T10:00:00Z"
  }
}
```

**Response — Failed**

```json
{
  "status": false,
  "message": "Unable to cancel. Shipment is already picked up."
}
```

---


### GET Shipment Label

```
GET /v1/shipments/label/{AWB}
```

Fetch the shipping label PDF URL for a given AWB number.

**Authorization:** Bearer Token

**Response — Success**

```json
{
  "status": true,
  "data": {
    "awb_number": "1100234987654",
    "label_url": "https://files.idiotship.tech/labels/20260512-label-1234.pdf"
  }
}
```

---

## Couriers

### GET Courier List

```
GET /v1/couriers
```

Returns the list of all active couriers available for the authenticated user's account (based on configured rate cards).

**Authorization:** Bearer Token

**Response — Success**

```json
{
  "status": true,
  "data": [
    {
      "id": 1,
      "name": "Xpressbees Air",
      "abbreviation": "XB-AIR",
      "available_modes": ["air"],
    },
    {
      "id": 2,
      "name": "Xpressbees Surface",
      "abbreviation": "XB-SUR",
      "available_modes": ["surface"],
    }
  ]
}
```

---

## Rate & Serviceability

### POST Check Rate & Serviceability

```
POST /v1/couriers/serviceability
```

Check which couriers service a route and get freight charges between origin and destination pincodes.

**Authorization:** Bearer Token

**Parameters**

| Field        | Required | Type    | Description                                    |
|--------------|----------|---------|------------------------------------------------|
| origin       | Yes      | string  | 6-digit pickup pincode                         |
| destination  | Yes      | string  | 6-digit delivery pincode                       |
| payment_type | Yes      | string  | Valid values: `prepaid`, `cod`                 |
| order_amount | Yes (COD)| float   | Selling price of the order (required for COD)  |
| weight       | No       | float   | Package weight in kg. Default: `0.5`           |
| length       | No       | integer | Package length in cm. Default: `10`            |
| breadth      | No       | integer | Package breadth in cm. Default: `10`           |
| height       | No       | integer | Package height in cm. Default: `10`            |

**Body**

```json
{
  "origin": "122001",
  "destination": "400001",
  "payment_type": "cod",
  "order_amount": 999.00,
  "weight": 0.5,
  "length": 20,
  "breadth": 15,
  "height": 10
}
```

**Response — Success**

```json
{
  "status": true,
  "data": [
    {
      "courier_id": 1,
      "courier_name": "Xpressbees Air",
      "mode": "air",
      "zone": "rest_of_india",
      "freight_charges": 68.00,
      "cod_charges": 28.50,
      "total_charges": 96.50,
      "base_weight_kg": 0.5,
      "chargeable_weight_kg": 0.5,
      "estimated_delivery_days": 2,
      "serviceable": true
    },
    {
      "courier_id": 2,
      "courier_name": "Xpressbees Surface",
      "mode": "surface",
      "zone": "rest_of_india",
      "freight_charges": 45.00,
      "cod_charges": 28.50,
      "total_charges": 73.50,
      "base_weight_kg": 0.5,
      "chargeable_weight_kg": 0.5,
      "estimated_delivery_days": 5,
      "serviceable": true
    }
  ]
}
```

**Response — Failed**

```json
{
  "status": false,
  "message": "Origin pincode must be exactly 6 digits."
}
```

---

## NDR (Non-Delivery Report)

### GET NDR List

```
GET /v1/ndr
```

Fetch the list of shipments with Non-Delivery Reports (exceptions raised by the courier during delivery attempt).

**Authorization:** Bearer Token

**Query Parameters**

| Param      | Required | Description                                         |
|------------|----------|-----------------------------------------------------|
| awb_number | No       | Comma-separated AWB list to filter specific records |
| page       | No       | Page number                                         |
| per_page   | No       | Records per page. Max: `250`                        |

**Response — Success**

```json
{
  "status": true,
  "data": [
    {
      "awb_number": "1100234987654",
      "order_id": "SZ10042",
      "order_number": "#1001",
      "event_date": "2026-05-11",
      "courier_remarks": "Customer Not Responding",
      "total_attempts": 1,
      "current_status": "ndr",
      "consignee": {
        "name": "Priya Verma",
        "phone": "9876543210",
        "city": "New Delhi"
      }
    }
  ]
}
```

**Response — Failed**

```json
{
  "status": false,
  "message": "No record found."
}
```

---

### POST Take NDR Action

```
POST /v1/ndr/action
```

Submit an action against NDR shipments. Actions allowed: re-attempt, change address, change phone. Up to 100 AWBs per request.

> **Note:** Action is only allowed when an exception has been raised by the courier.

**Authorization:** Bearer Token

**Body**

```json
[
  {
    "awb": "1100234987654",
    "action": "re-attempt",
    "action_data": {
      "re_attempt_date": "2026-05-14"
    }
  },
  {
    "awb": "1100234987655",
    "action": "change_address",
    "action_data": {
      "name": "Priya Verma",
      "address_1": "C-12, Lajpat Nagar",
      "address_2": "Near Central Market",
      "city": "New Delhi",
      "state": "Delhi",
      "pincode": "110024",
      "phone": "9876543210"
    }
  },
  {
    "awb": "1100234987656",
    "action": "change_phone",
    "action_data": {
      "phone": "9876543211"
    }
  }
]
```

**Supported Actions**

| Action         | Required Fields in action_data                                              |
|----------------|-----------------------------------------------------------------------------|
| re-attempt     | `re_attempt_date` (YYYY-MM-DD)                                              |
| change_address | `name`, `address_1`, `address_2`, `city`, `state`, `pincode`, `phone`      |
| change_phone   | `phone` (10-digit)                                                          |

**Response — Success**

```json
[
  {
    "status": true,
    "awb": "1100234987654",
    "message": "NDR action submitted successfully."
  },
  {
    "status": false,
    "awb": "1100234987655",
    "message": "No courier exception available for this AWB."
  }
]
```

---


## Hubs (Pickup Addresses)

### GET Hub List

```
GET /v1/hubs
```

Returns all active pickup hubs configured for the authenticated user.

**Authorization:** Bearer Token

**Response — Success**

```json
{
  "status": true,
  "data": [
    {
      "id": 5,
      "name": "Main Warehouse",
      "contact_person": "Amit Kumar",
      "address_line1": "140, MG Road",
      "address_line2": "Near Metro Station",
      "city": "Gurugram",
      "state": "Haryana",
      "pin_code": "122001",
      "country": "India",
      "phone": "9999999999",
      "gstin": "18AABCU9603R1ZM",
      "is_primary": true,
      "is_active": true
    }
  ]
}
```

---

### POST Create Hub

```
POST /v1/hubs
```

Create a new pickup hub / warehouse address.

**Authorization:** Bearer Token

**Parameters**

| Field         | Required | Type   | Description                           |
|---------------|----------|--------|---------------------------------------|
| name          | Yes      | string | Unique hub name. Max 100 chars        |
| contact_person| No       | string | Contact person name                   |
| address_line1 | Yes      | string | Primary address                       |
| address_line2 | No       | string | Secondary address                     |
| city          | Yes      | string | City                                  |
| state         | Yes      | string | State                                 |
| pin_code      | Yes      | string | 6-digit pincode                       |
| phone         | Yes      | string | 10-digit contact phone                |
| gstin         | No       | string | 15-char GSTIN                         |
| is_primary    | No       | bool   | Set as primary hub. Default: `false`  |

**Body**

```json
{
  "name": "Delhi Warehouse",
  "contact_person": "Suresh Sharma",
  "address_line1": "B-12, Okhla Industrial Area",
  "address_line2": "Phase 2",
  "city": "New Delhi",
  "state": "Delhi",
  "pin_code": "110020",
  "phone": "9876543210",
  "gstin": "07AABCU9603R1ZM",
  "is_primary": false
}
```

**Response — Success**

```json
{
  "status": true,
  "data": {
    "id": 6,
    "name": "Delhi Warehouse",
    "city": "New Delhi",
    "state": "Delhi",
    "pin_code": "110020",
    "is_primary": false,
    "is_active": true
  }
}
```

**Response — Failed**

```json
{
  "status": false,
  "message": "A hub with this name already exists."
}
```

---

## Response Conventions

All API responses follow a consistent envelope format:

```json
{
  "status": true | false,
  "data": { ... },
  "message": "Human-readable message (on errors or informational responses)"
}
```

| Field   | Type    | Description                              |
|---------|---------|------------------------------------------|
| status  | boolean | `true` on success, `false` on failure    |
| data    | object  | Response payload (present on success)    |
| message | string  | Error or informational message (on failure or where applicable) |

---

## Error Codes

| HTTP Status | Meaning                                                  |
|-------------|----------------------------------------------------------|
| 200         | Success                                                  |
| 400         | Bad Request — validation error or missing required field |
| 401         | Unauthorized — missing or invalid Bearer token           |
| 403         | Forbidden — action not allowed for your account role     |
| 404         | Not Found — record does not exist                        |
| 422         | Unprocessable Entity — business rule violation (e.g. insufficient balance, blocked pincode) |
| 500         | Internal Server Error                                    |

### Common Error Responses

**401 Unauthorized**
```json
{
  "status": false,
  "message": "Authentication credentials were not provided or are invalid."
}
```

**403 Forbidden**
```json
{
  "status": false,
  "message": "You do not have permission to perform this action."
}
```

**422 Business Rule Violation**
```json
{
  "status": false,
  "message": "Insufficient wallet balance. Current balance: ₹20.00, required: ₹80.00."
}
```

**500 Internal Server Error**
```json
{
  "status": false,
  "message": "An unexpected error occurred. Please try again or contact support."
}
```

---

*IdiotShip API Documentation — For integration support, contact your account manager.*