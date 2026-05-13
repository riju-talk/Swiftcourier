import logging
import requests

from zeep import Client, Settings
from zeep.transports import Transport


logger = logging.getLogger("my-logger")

WSDL_URL = "https://customerapitesting.tciexpress.in/ServiceEnquire.asmx?wsdl"


# ==========================================================
# SESSION MANAGEMENT
# ==========================================================
def create_soap_client():
    session = requests.Session()

    adapter = requests.adapters.HTTPAdapter(
        pool_connections=50,
        pool_maxsize=50,
    )

    session.mount("https://", adapter)

    transport = Transport(session=session, timeout=20)

    settings = Settings(strict=False, xml_huge_tree=True)

    client = Client(
        wsdl=WSDL_URL,
        transport=transport,
        settings=settings,
    )

    return client


SOAP_CLIENT = create_soap_client()


# ==========================================================
# BASE REQUEST
# ==========================================================
def soap_request(operation: str, payload: dict):
    global SOAP_CLIENT

    try:
        service = SOAP_CLIENT.service
        func = getattr(service, operation)

        response = func(**payload)

        return response

    except Exception:
        logger.exception("SOAP request failed. Recreating client...")
        SOAP_CLIENT = create_soap_client()

        service = SOAP_CLIENT.service
        func = getattr(service, operation)

        return func(**payload)


def build_payload(order, hub):
    items = []
    for item in order.orderitem_set.all():
        items.append(
            {
                "ProductName": item.product.name,
                "Qty": item.quantity,
                "Price": float(item.unit_price),
            }
        )

    payload = {
        "CustomerName": order.shipping_address.name,
        "Address": order.shipping_address.line1,
        "Pincode": order.shipping_address.pin_code,
        "Mobile": order.shipping_address.phone,
        "OrderNo": order.get_order_id(),
        "CODAmount": order.total_amount if order.payment.method == "cod" else 0,
        "Weight": order.shipment.package_weight_kg,
        "Pieces": len(items),
    }

    return payload, None


def order_booking(payload):
    return soap_request(
        operation="CreateShipment",  # ⚠️ real name from WSDL
        payload=payload,
    )


def track_shipment(awb_number: str):
    return soap_request("TrackConsignment", {"AWBNo": awb_number})


def cancel_shipment(awb_number: str):
    return soap_request("CancelShipment", {"AWBNo": awb_number})


def ship_order(
    order,
    hub,
    courier_abbreviation,
):
    try:
        payload, err = build_payload(order, hub)

        if not payload:
            return False, {"error": err}

        res = order_booking(payload)

        awb_no = res.AWBNo

        order.awb_number = awb_no
        order.hub = hub
        order.update_status("pending_pickup")
        order.save()

        return True, awb_no
    except Exception as e:
        logger.exception("TCI Ship Order Exception")
        return False, {"error": str(e)}


print(
    soap_request(
        "getToken",
        {
            "username": "tciapi",
            "password": "tci@123",
        },
    )
)
