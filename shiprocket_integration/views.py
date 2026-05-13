import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from order_manager.models import Order


logger = logging.getLogger("my-logger")


# Create your views here.
@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"})

    try:
        data = request.body.decode("utf-8")
        if not data or data == "":
            return JsonResponse({"error": "Empty payload"})

        payload = json.loads(data)
        logger.debug(f"Shiprocket Webhook:: payload: {payload}")

        awb = payload.get("awb")
        status = payload.get("current_status")

        if not awb or not status:
            return JsonResponse({"error": "tracking_number or status missing"})

        # 1️⃣ Map Shiprocket -> Internal Order statuses
        status_map = {
            "AWB ASSIGNED": "pending_pickup",
            "LABEL GENERATED": "pending_pickup",
            "PICKUP SCHEDULED/GENERATED": "pending_pickup",
            "PICKUP QUEUED": "pending_pickup",
            "MANIFEST GENERATED": "pending_pickup",
            "SHIPPED": "in_transit",
            "DELIVERED": "delivered",
            "CANCELLED": "ready_to_ship",
            "RTO INITIATED": "rto",
            "RTO DELIVERED": "rto_delivered",
            "PENDING": "pending_pickup",
            "LOST": "lost",
            "PICKUP ERROR": "pending_pickup",
            "RTO ACKNOWLEDGED": "rto",
            "PICKUP RESCHEDULED": "pending_pickup",
            "CANCELLATION REQUESTED": "ready_to_ship",
            "OUT FOR DELIVERY": "out_for_delivery",
            "IN TRANSIT": "in_transit",
            "OUT FOR PICKUP": "pending_pickup",
            "PICKUP EXCEPTION": "pending_pickup",
            "UNDELIVERED": "ndr",
            "DELAYED": "in_transit",
            "PARTIAL_DELIVERED": "delivered",
            "DESTROYED": "in_transit",
            "DAMAGED": "damaged",
            "FULFILLED": "delivered",
            "REACHED AT DESTINATION": "in_transit",
            "REACHED AT DESTINATION HUB": "in_transit",
            "MISROUTED": "in_transit",
            "RTO NDR": "rto",
            "RTO OFD": "rto_out_for_delivery",
            "PICKED UP": "in_transit",
            "SELF FULFILLED": "in_transit",
            "DISPOSED_OFF": "in_transit",
            "CANCELLED_BEFORE_DISPATCHED": "cancelled",
            "RTO_IN_TRANSIT": "rto_in_transit",
            "RTO IN TRANSIT": "rto_in_transit",
            "QC FAILED": "delivered",
            "REACHED WAREHOUSE": "in_transit",
            "CUSTOM CLEARED": "in_transit",
            "IN FLIGHT": "in_transit",
            "HANDOVER TO COURIER": "pending_pickup",
            "SHIPMENT BOOKED": "pending_pickup",
            "IN TRANSIT OVERSEAS": "in_transit",
            "CONNECTION ALIGNED": "in_transit",
            "REACHED OVERSEAS WAREHOUSE": "in_transit",
            "CUSTOM CLEARED OVERSEAS": "in_transit",
            "BOX PACKING": "pending_pickup",
        }

        internal_status = status_map.get(status)

        if not internal_status:
            logger.warning(f"Shiprocket Webhook:: Unknown status: {status}")
            return JsonResponse({"message": "Status ignored (unknown)"})

        # 2️⃣ Fetch order by AWB
        try:
            order = Order.objects.get(
                awb_number=awb, logistic_partner__abbreviation__startswith="sr_"
            )
        except Order.DoesNotExist:
            logger.error(f"Shiprocket Webhook:: Order with AWB {awb} not found")
            return JsonResponse({"error": "Order not found"})
        except Exception as e:
            logger.error(f"Shiprocket Webhook:: Error fetching order with AWB {awb}: {str(e)}")
            return JsonResponse({"error": "Internal error"})

        # 3️⃣ Update order
        previous_status = order.status
        order.update_status(internal_status)

        # Save webhook raw JSON inside order.json for logs
        order.json |= payload
        order.save(update_fields=["status", "json"])

        logger.info(
            f"Shiprocket Webhook:: Order #{order.id} ({awb}) updated {previous_status} -> {internal_status}"
        )

        return JsonResponse({"message": "Webhook processed successfully"})

    except Exception as e:
        logger.error(f"Shiprocket Webhook:: error: {str(e)}")
        return JsonResponse({"error": "Internal error"})
