import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from order_manager.models import Order


logger = logging.getLogger("my-logger")


# Create your views here.
@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed, only POST method allowed"}, status=405
        )

    try:
        data = request.body.decode("utf-8")
        if not data or data == "":
            return JsonResponse({"error": "Empty payload"})

        payload = json.loads(data)
        logger.debug(f"TCI Webhook:: payload: {payload}")

        awb = payload.get("awb")
        status = payload.get("status")

        if not awb or not status:
            return JsonResponse({"error": "tracking_number or status missing"})

        # 1️⃣ Map TCI -> Internal Order statuses
        status_map = {
            "Booked": "pending_pickup",
            "Order Cancelled": "ready_to_ship",
            "Pickup Initiated": "pending_pickup",
            "Pickup Cancelled": "pending_pickup",
            "Pickup Pending": "pending_pickup",
            "Pickup Completed": "in_transit",
            "In Transit": "in_transit",
            "Undelivered": "ndr",
            "Out For Delivery": "out_for_delivery",
            "Delivered": "delivered",
            "RTO": "rto",
            "RTO In Transit": "rto_in_transit",
            "RTO Delivered": "rto_delivered",
            "Shipment Lost": "lost",
            "Shipment Damaged": "damaged",
            "Out for Pickup": "pending_pickup",
        }

        internal_status = status_map.get(status)

        if not internal_status:
            logger.warning(f"TCI Webhook:: Unknown status from TCI: {status}")
            return JsonResponse({"message": "Status ignored (unknown)"})

        # 2️⃣ Fetch order by AWB
        try:
            order = Order.objects.get(
                awb_number=awb, logistic_partner__abbreviation__startswith="tci_"
            )
        except Order.DoesNotExist:
            logger.error(f"TCI Webhook:: Order with AWB {awb} not found")
            return JsonResponse({"error": "Order not found"})
        except Exception as e:
            logger.error(f"TCI Webhook:: Error fetching order with AWB {awb}: {str(e)}")
            return JsonResponse({"error": "Internal error"})

        # 3️⃣ Update order
        previous_status = order.status
        order.update_status(internal_status)

        # Save webhook raw JSON inside order.json for logs
        order.json |= payload
        order.save(update_fields=["status", "json"])

        logger.info(
            f"TCI Webhook:: Order #{order.id} ({awb}) updated {previous_status} -> {internal_status}"
        )

        return JsonResponse({"message": "Webhook processed successfully"})

    except Exception as e:
        logger.error(f"TCI Webhook:: error: {str(e)}")
        return JsonResponse({"error": "Internal error"})
