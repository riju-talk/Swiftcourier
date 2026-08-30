import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from order_manager.webhook_events import log_carrier_webhook
from account.models import Courier
from order_manager.models import Order


logger = logging.getLogger("my-logger")


@csrf_exempt
@log_carrier_webhook("parcelx")
def webhook(request):
    """
    {
        "awb": "78098079312",
        "status_code": "233",
        "status_description": "Consignee'S Address Incomplete/Incorrect",
        "status_location": "Jhilmil E-Tail Centre",
        "event_date": "2025-11-26 19:23:00",
        "client_order_id": "123456",
        "status_title": "NDR",
    }
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
        logger.debug(f"Parcelx Webhook:: Payload: {payload}")

        awb = payload.get("awb")
        status_title = payload.get("status_title")

        if not awb:
            return JsonResponse({"error": "awb missing"}, status=400)

        if not status_title:
            return JsonResponse({"error": "status_title missing"}, status=400)

        # 1️⃣ MAP USING STATUS TITLE ONLY
        title_map = {
            "Pickup Pending": "pending_pickup",
            "Out for Pickup": "pending_pickup",
            "Picked": "in_transit",
            "In Transit": "in_transit",
            "Out For Delivery": "out_for_delivery",
            "Delivered": "delivered",
            "Cancelled": "ready_to_ship",
            "Shipment Exception": "exception",
            "RTO Initiated": "rto",
            "RTO In Transit": "rto_in_transit",
            "RTO Out For Delivery": "rto_out_for_delivery",
            "RTO Delivered": "rto_delivered",
            "NDR": "ndr",
        }

        internal_status = title_map.get(status_title, "in_transit")

        # 2️⃣ ORDER LOOKUP
        try:
            order = Order.objects.get(
                awb_number=awb, logistic_partner=Courier.objects.get(abbreviation="px")
            )
        except Order.DoesNotExist:
            logger.error(f"Parcelx Webhook:: Order with AWB {awb} not found")
            return JsonResponse({"error": "Order not found"}, status=404)
        except Exception as e:
            logger.error(f"Parcelx Webhook:: Error retrieving order with AWB {awb}: {str(e)}")
            return JsonResponse({"error": "internal server error"}, status=500)

        # 3️⃣ UPDATE ORDER STATUS
        previous = order.status
        order.update_status(internal_status)

        # Save webhook JSON
        order.json |= payload
        order.save(update_fields=["json"])

        logger.info(
            f"Parcelx Webhook:: Order #{order.id} ({awb}) updated: {previous} -> {internal_status}"
        )

        return JsonResponse({"message": "Webhook processed successfully"})

    except Exception as e:
        logger.error(f"Parcelx Webhook:: Error: {str(e)}", exc_info=True)
        return JsonResponse({"error": "internal server error"}, status=500)
