"""
SmartShip API Test File
=======================
Run:  python test_smartship.py
Outputs a full JSON report to:  smartship_test_results.json

To grab courier IDs specifically, look at:
  - serviceability_carriers  (from Hub Serviceability API)
  - rate_calculator_carriers (from Rate Calculator API)
  - carrier_serviceable_pincodes (from Carrier Pincodes API — pass "all")
"""

import json
import hashlib
import logging
import os
import sys
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("smartship-test")

# ── Test credentials (from SmartShip API docs) ─────────────────────────────
# Replace with your live credentials when ready
CREDS = {
    "username": "idiotship.tech@gmail.com",
    "password": "5623ad986e6f23d225a1732dd6155657",  # plain password → MD5'd below
    "client_id": "WWI4JHPBC7H5LTWQC5WV8HORPCFZ2",
    "client_secret": "0W8HM2TBM&$5*DQ&B+RU*U",
    "grant_type":"password"
}
# CREDS["password_md5"] = hashlib.md5(CREDS["password_plain"].encode()).hexdigest()

OAUTH_URL = "https://oauth.smartship.in"
BASE_URL = "https://api.smartship.in"

# Filled in after login
TOKEN = ""

# ── Test config (adjust to your account) ──────────────────────────────────
TEST_HUB_PINCODE = 122001  # Gurgaon — used for serviceability checks
TEST_DEST_PINCODE = 110001  # Delhi
TEST_HUB_ID = None  # set after hub registration
TEST_CLIENT_ORDER_ID = f"TEST_SHIPZEE_{datetime.now().strftime('%Y%m%d%H%M%S')}"
TEST_REQUEST_ORDER_ID = None  # set after order booking


# ==========================================================================
# SESSION
# ==========================================================================
def _make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    return s


SESSION = _make_session()


def _req(method: str, url: str, payload=None, auth=True) -> dict:
    """Raw request helper — returns parsed JSON or an error dict."""
    headers = {}
    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(payload) if payload is not None else None
    try:
        r = SESSION.request(
            method.upper(), url, headers=headers, data=body, timeout=(5, 30)
        )
        return r.json()
    except Exception as e:
        return {"_error": str(e)}


# ==========================================================================
# RESULT COLLECTOR
# ==========================================================================
results = {}


def record(key: str, data: dict):
    logger.info("%-45s → status=%s", key, data.get("status", data.get("_error", "?")))
    results[key] = data


# ==========================================================================
# 1. LOGIN TOKEN
# ==========================================================================
def test_login():
    global TOKEN
    logger.info("=" * 60)
    logger.info("1. LOGIN TOKEN")
    data = _req(
        "POST",
        f"{OAUTH_URL}/loginToken.php",
        {
            "username": CREDS["username"],
            "password": CREDS["password"],
            "client_id": CREDS["client_id"],
            "client_secret": CREDS["client_secret"],
            "grant_type": "password",
        },
        auth=False,
    )
    record("1_login_token", data)
    if "access_token" in data:
        TOKEN = data["access_token"]
        logger.info("   ✓ Token obtained: %s...%s", TOKEN[:6], TOKEN[-6:])
    else:
        logger.error("   ✗ Login failed — remaining tests will fail auth")
    return TOKEN


# ==========================================================================
# 2. HUB REGISTRATION
# ==========================================================================
def test_hub_registration():
    global TEST_HUB_ID
    logger.info("=" * 60)
    logger.info("2. HUB REGISTRATION")
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/hubRegistration",
        {
            "hub_details": {
                "hub_name": "Idiotship Test Warehouse",
                "pincode": str(TEST_HUB_PINCODE),
                "city": "Gurgaon",
                "state": "Haryana",
                "address1": "G-167, Sector 40",
                "address2": "Near Police Station",
                "hub_phone": "9999613323",
                "delivery_type_id": 2,
            }
        },
    )
    record("2_hub_registration", data)
    if data.get("status") == 1:
        TEST_HUB_ID = data.get("data", {}).get("hub_id")
        logger.info("   ✓ Hub registered. hub_id = %s", TEST_HUB_ID)
    return data


# ==========================================================================
# 3. GET HUB DETAILS
# ==========================================================================
def test_get_hub_details():
    logger.info("=" * 60)
    logger.info("3. GET HUB DETAILS")
    # pass "" to list all hubs
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/getHubDetail",
        {"hub_ids": "" if not TEST_HUB_ID else [TEST_HUB_ID]},
    )
    record("3_get_hub_details", data)
    if data.get("status") == 1:
        hubs = data.get("data", {}).get("valid_hubs", {})
        logger.info("   ✓ Valid hubs returned: %s", list(hubs.keys()))
    return data


# ==========================================================================
# 4. UPDATE HUB DETAILS
# ==========================================================================
def test_update_hub():
    if not TEST_HUB_ID:
        logger.warning("4. UPDATE HUB — skipped (no hub_id)")
        return {}
    logger.info("=" * 60)
    logger.info("4. UPDATE HUB DETAILS  hub_id=%s", TEST_HUB_ID)
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/updateHubDetails",
        {
            "hub_id": str(TEST_HUB_ID),
            "hub_name": "Idiotship Test Warehouse (updated)",
            "hub_phone": "9999613323",
            "pincode": str(TEST_HUB_PINCODE),
            "city": "Gurgaon",
            "state": "Haryana",
            "address1": "G-167, Sector 40",
            "address2": "Near Police Station",
        },
    )
    record("4_update_hub", data)
    return data


# ==========================================================================
# 5. HUB SERVICEABILITY  ← courier IDs live here
# ==========================================================================
def test_hub_serviceability():
    if not TEST_HUB_ID:
        logger.warning("5. HUB SERVICEABILITY — skipped (no hub_id)")
        return {}
    logger.info("=" * 60)
    logger.info(
        "5. HUB SERVICEABILITY  hub_id=%s → pincode=%s", TEST_HUB_ID, TEST_DEST_PINCODE
    )
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/ServiceabilityHubWise",
        {
            "order_info": {
                "hub_ids": [TEST_HUB_ID],
                "destination_pincode": TEST_DEST_PINCODE,
                "order_weight": 500,
            },
            "request_info": {
                "extra_info": True,  # ← gives us carrier lists
                "cost_info": True,
            },
        },
    )
    record("5_hub_serviceability", data)
    # Pretty-print carrier info
    hub_data = data.get("data", {}).get("hub_serviceability", {})
    for hid, info in hub_data.items():
        for key in ("pickup_service_carriers", "delivery_service_carriers"):
            carriers = info.get(key)
            if carriers:
                logger.info("   ✓ %s carriers for hub %s: %s", key, hid, carriers)
    return data


# ==========================================================================
# 6. RATE CALCULATOR  ← another source of carrier IDs
# ==========================================================================
def test_rate_calculator():
    logger.info("=" * 60)
    logger.info("6. RATE CALCULATOR  %s → %s", TEST_HUB_PINCODE, TEST_DEST_PINCODE)
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/rateCalculator",
        {
            "order_info": {
                "email": CREDS["username"],
                "source_pincode": TEST_HUB_PINCODE,
                "destination_pincode": TEST_DEST_PINCODE,
                "order_weight": 500,
                "order_value": 1000,
                "payment_type": "cod",
                "length": "10",
                "width": "10",
                "height": "10",
                "shipment_type": "forward",
                "preferred_carriers": [1, 3, 279],
            },
            "request_info": {"extra_info": True},
        },
    )
    record("6_rate_calculator", data)
    carriers = data.get("data", {}).get("carrier_info", {})
    if carriers:
        logger.info("   ✓ Carriers from rate calculator:")
        for rank, info in carriers.items():
            logger.info(
                "      [%s] id=%-5s  name=%s  cost=%s  tat=%s days",
                rank,
                info.get("carrier_id"),
                info.get("carrier_name"),
                info.get("cost"),
                info.get("tat"),
            )
    return data


# ==========================================================================
# 7. CARRIER SERVICEABLE PINCODES  ← pass "all" to get every carrier
# ==========================================================================
def test_carrier_pincodes():
    logger.info("=" * 60)
    logger.info("7. CARRIER SERVICEABLE PINCODES  (carrier_id=all)")
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/CarrierServiceablePincodes",
        {
            "carrier_info": {
                "payment_type": "",
                "carrier_id": ["all"],
            }
        },
    )
    record("7_carrier_pincodes", data)
    if data.get("status") == 1:
        for cid, info in data.get("data", {}).items():
            if isinstance(info, dict):
                logger.info(
                    "   carrier_id=%-5s  valid_pincodes=%s",
                    cid,
                    info.get("valid_pincode", {}).get("count"),
                )
    return data


# ==========================================================================
# 8. ONE-STEP ORDER REGISTRATION
# ==========================================================================
def test_order_registration():
    global TEST_REQUEST_ORDER_ID
    if not TEST_HUB_ID:
        logger.warning("8. ORDER REGISTRATION — skipped (no hub_id)")
        return {}
    logger.info("=" * 60)
    logger.info("8. ONE-STEP ORDER REGISTRATION  order_id=%s", TEST_CLIENT_ORDER_ID)
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/orderRegistrationOneStep",
        {
            "request_info": {
                "client_id": CREDS["client_id"],
                "run_type": "create",
            },
            "orders": [
                {
                    "client_order_reference_id": TEST_CLIENT_ORDER_ID,
                    "shipment_type": 1,
                    "order_collectable_amount": "500",
                    "total_order_value": "500",
                    "payment_type": "cod",
                    "package_order_weight": "300",
                    "package_order_length": "12",
                    "package_order_height": "5",
                    "package_order_width": "8",
                    "shipper_hub_id": str(TEST_HUB_ID),
                    "shipper_gst_no": "",
                    "order_invoice_date": datetime.now().strftime("%d-%m-%Y"),
                    "order_invoice_number": TEST_CLIENT_ORDER_ID,
                    "product_details": [
                        {
                            "client_product_reference_id": "SKU001",
                            "product_name": "Test Product",
                            "product_category": "general",
                            "product_hsn_code": "",
                            "product_quantity": "1",
                            "product_invoice_value": "500",
                            "product_gst_tax_rate": "",
                            "product_taxable_value": "500",
                            "product_sgst_amount": "",
                            "product_sgst_tax_rate": "",
                            "product_cgst_amount": "",
                            "product_cgst_tax_rate": "",
                        }
                    ],
                    "consignee_details": {
                        "consignee_name": "Test Customer",
                        "consignee_phone": "9876543210",
                        "consignee_email": "test@idiotship.tech",
                        "consignee_complete_address": "Plot 1268, Sector 46, Near Park",
                        "consignee_pincode": str(TEST_DEST_PINCODE),
                    },
                }
            ],
        },
    )
    record("8_order_registration", data)
    orders = data.get("data", {}).get("success_order_details", {}).get("orders", [])
    if orders:
        o = orders[0]
        TEST_REQUEST_ORDER_ID = o.get("request_order_id")
        awb = o.get("awb_number")
        carrier = o.get("carrier_name")
        logger.info(
            "   ✓ request_order_id=%s  awb=%s  carrier=%s",
            TEST_REQUEST_ORDER_ID,
            awb,
            carrier,
        )
    return data


# ==========================================================================
# 9. GET ORDER DETAILS
# ==========================================================================
def test_get_order_details():
    if not TEST_REQUEST_ORDER_ID:
        logger.warning("9. GET ORDER DETAILS — skipped (no request_order_id)")
        return {}
    logger.info("=" * 60)
    logger.info("9. GET ORDER DETAILS  request_order_id=%s", TEST_REQUEST_ORDER_ID)
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/orderDetails",
        {
            "filters": {
                "filter_type": {
                    "and": {
                        "request_order_id": str(TEST_REQUEST_ORDER_ID),
                    }
                }
            },
            "limit": {"offset": 0, "limit": 1},
        },
    )
    record("9_get_order_details", data)
    orders = data.get("data", {}).get("orders_details", {})
    for oid, info in orders.items():
        meta = info.get("order_meta_details", {})
        awb = meta.get("awb_no", {}).get("awb_no")
        carrier = meta.get("carrier_name", {}).get("carrier_name")
        status = info.get("order_details", {}).get("status_description")
        logger.info(
            "   ✓ order=%s  awb=%s  carrier=%s  status=%s", oid, awb, carrier, status
        )
    return data


# ==========================================================================
# 10. SHIPPING LABEL
# ==========================================================================
def test_shipping_label():
    if not TEST_REQUEST_ORDER_ID:
        logger.warning("10. SHIPPING LABEL — skipped (no request_order_id)")
        return {}
    logger.info("=" * 60)
    logger.info("10. SHIPPING LABEL  client_order_ref_id=%s", TEST_CLIENT_ORDER_ID)
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/getShippingLabels",
        {
            "client_order_ref_id": TEST_CLIENT_ORDER_ID,
        },
    )
    record("10_shipping_label", data)
    url = data.get("data", {}).get("url")
    if url:
        logger.info("   ✓ Label URL: %s", url)
    return data


# ==========================================================================
# 11. CREATE MANIFEST
# ==========================================================================
def test_create_manifest():
    if not TEST_CLIENT_ORDER_ID:
        logger.warning("11. CREATE MANIFEST — skipped")
        return {}
    logger.info("=" * 60)
    logger.info(
        "11. CREATE MANIFEST  client_order_reference_id=%s", TEST_CLIENT_ORDER_ID
    )
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/createManifest",
        {
            "client_order_reference_ids": [TEST_CLIENT_ORDER_ID],
            "preferred_pickup_date": "",
            "shipment_type": 1,
        },
    )
    record("11_create_manifest", data)
    summary = data.get("data", {}).get("summary", {})
    pdf = summary.get("manifest_pdf", {}).get("manifest_url")
    if pdf:
        logger.info("   ✓ Manifest PDF: %s", pdf)
    return data


# ==========================================================================
# 12. TRACK SHIPMENT
# ==========================================================================
def test_track_shipment():
    # Use the AWB from order registration if available
    awb = (
        results.get("8_order_registration", {})
        .get("data", {})
        .get("success_order_details", {})
        .get("orders", [{}])[0]
        .get("awb_number")
    )
    if not awb:
        logger.warning("12. TRACK SHIPMENT — skipped (no AWB)")
        return {}
    logger.info("=" * 60)
    logger.info("12. TRACK SHIPMENT  awb=%s", awb)
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        r = SESSION.get(
            f"{BASE_URL}/v1/Trackorder",
            params={"tracking_numbers": awb},
            headers=headers,
            timeout=(5, 30),
        )
        data = r.json()
    except Exception as e:
        data = {"_error": str(e)}
    record("12_track_shipment", data)
    scans = data.get("data", {}).get("scans", {})
    for awb_key, scan_list in scans.items():
        if scan_list:
            latest = scan_list[0]
            logger.info(
                "   ✓ Latest scan: %s | %s | %s",
                latest.get("date_time"),
                latest.get("location"),
                latest.get("action"),
            )
    return data


# ==========================================================================
# 13. NDR LIST  (orders in delivery-attempted statuses)
# ==========================================================================
def test_ndr_list():
    logger.info("=" * 60)
    logger.info("13. NDR LIST  (status codes 12-18, 22, 23)")
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/orderDetails",
        {
            "filters": {
                "filter_type": {
                    "and": {
                        "status": {
                            "status_code": "12,13,14,15,16,17,18,22,23",
                            "check_type": "Y",
                        }
                    }
                }
            },
            "limit": {"offset": 0, "limit": 10},
        },
    )
    record("13_ndr_list", data)
    total = data.get("data", {}).get("summary", {}).get("total_records", 0)
    logger.info("   ✓ NDR orders found: %s", total)
    return data


# ==========================================================================
# 14. NDR ACTION  (reattempt)
# ==========================================================================
def test_ndr_action():
    if not TEST_REQUEST_ORDER_ID:
        logger.warning("14. NDR ACTION — skipped (no request_order_id)")
        return {}
    logger.info("=" * 60)
    logger.info(
        "14. NDR ACTION (reattempt)  request_order_id=%s", TEST_REQUEST_ORDER_ID
    )
    next_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/orderReattempt",
        {
            "orders": [
                {
                    "request_order_id": str(TEST_REQUEST_ORDER_ID),
                    "action_id": "1",  # 1=reattempt, 2=RTO
                    "comments": "Customer requested re-delivery",
                    "next_attempt_date": next_date,
                    "client_order_reference_id": [""],
                    "address": "Plot 1268, Sector 46, Near Park",
                    "phone": 9876543210,
                    "names": "Test Customer",
                    "alternate_address": "",
                    "alternate_number": "",
                }
            ]
        },
    )
    record("14_ndr_action", data)
    return data


# ==========================================================================
# 15. CANCEL ORDER
# ==========================================================================
def test_cancel_order():
    if not TEST_CLIENT_ORDER_ID:
        logger.warning("15. CANCEL ORDER — skipped")
        return {}
    logger.info("=" * 60)
    logger.info("15. CANCEL ORDER  client_order_reference_id=%s", TEST_CLIENT_ORDER_ID)
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/orderCancellation",
        {
            "request_info": {
                "ip_address": "",
                "browser_name": "",
                "location": "",
            },
            "orders": {
                "client_order_reference_ids": [TEST_CLIENT_ORDER_ID],
                "request_order_ids": [],
            },
        },
    )
    record("15_cancel_order", data)
    cancellation = data.get("data", {}).get("order_cancellation_details", {})
    logger.info(
        "   successful=%s  failed=%s",
        cancellation.get("successful"),
        list(cancellation.get("failure", {}).keys()),
    )
    return data


# ==========================================================================
# 16. DELETE HUB  (cleanup — run last)
# ==========================================================================
def test_delete_hub():
    if not TEST_HUB_ID:
        logger.warning("16. DELETE HUB — skipped (no hub_id)")
        return {}
    logger.info("=" * 60)
    logger.info("16. DELETE HUB  hub_id=%s", TEST_HUB_ID)
    data = _req(
        "POST",
        f"{BASE_URL}/v2/app/Fulfillmentservice/deleteHub",
        {"hub_ids": [TEST_HUB_ID]},
    )
    record("16_delete_hub", data)
    return data


# ==========================================================================
# COURIER SUMMARY  — extract all carrier IDs from collected results
# ==========================================================================
def print_courier_summary():
    logger.info("")
    logger.info("=" * 60)
    logger.info("COURIER / CARRIER ID SUMMARY")
    logger.info("=" * 60)

    found: dict[str, str] = {}  # id → name

    # From rate calculator
    carriers = (
        results.get("6_rate_calculator", {}).get("data", {}).get("carrier_info", {})
    )
    for info in carriers.values():
        cid = str(info.get("carrier_id", ""))
        name = info.get("carrier_name", "")
        if cid:
            found[cid] = name

    # From hub serviceability (extra_info=True returns carrier lists)
    hub_svc = (
        results.get("5_hub_serviceability", {})
        .get("data", {})
        .get("hub_serviceability", {})
    )
    for hub_info in hub_svc.values():
        for key in ("pickup_service_carriers", "delivery_service_carriers"):
            for c in hub_info.get(key) or []:
                cid = str(c.get("carrier_id") or c.get("id") or "")
                name = c.get("carrier_name") or c.get("name") or ""
                if cid:
                    found[cid] = name

    # From carrier pincodes (keys are carrier IDs)
    pincode_data = results.get("7_carrier_pincodes", {}).get("data", {})
    for cid, info in pincode_data.items():
        if isinstance(info, dict) and cid not in found:
            found[cid] = ""  # name not returned by this endpoint

    if found:
        logger.info("  %-10s  %s", "carrier_id", "carrier_name")
        logger.info("  %-10s  %s", "-" * 10, "-" * 30)
        for cid, name in sorted(found.items(), key=lambda x: x[0].zfill(6)):
            logger.info("  %-10s  %s", cid, name or "(name not returned)")
    else:
        logger.info("  No carrier data found — check if credentials are valid")

    results["_courier_summary"] = found


# ==========================================================================
# MAIN
# ==========================================================================
if __name__ == "__main__":
    logger.info("SmartShip API Test Suite — %s", datetime.now().isoformat())

    test_login()

    if TOKEN:
        test_hub_registration()
        test_get_hub_details()
        test_update_hub()
        test_hub_serviceability()  # ← courier IDs
        test_rate_calculator()  # ← courier IDs
        test_carrier_pincodes()  # ← courier IDs
        test_order_registration()
        test_get_order_details()
        test_shipping_label()
        test_create_manifest()
        test_track_shipment()
        test_ndr_list()
        test_ndr_action()
        test_cancel_order()
        test_delete_hub()  # cleanup last

    print_courier_summary()

    # ── Dump full results to JSON ──────────────────────────────────────────
    out_file = "smartship_test_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info("")
    logger.info("Full results written to: %s", out_file)
    logger.info("Tests complete.")
