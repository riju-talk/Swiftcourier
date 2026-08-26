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
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = request.body.decode("utf-8")
        if not data or data == "":
            return JsonResponse({"error": "Empty payload"}, status=400)

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            logger.warning(f"Jiffy Webhook:: Invalid JSON payload: {data!r}")
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        logger.debug(f"Jiffy Webhook:: payload: {payload}")

        awb = payload.get("awb_number")
        status = payload.get("status")

        if not awb or not status:
            return JsonResponse({"error": "tracking_number or status missing"}, status=400)

        # 1️⃣ Map Jiffy -> Internal Order statuses
        status_map = {
            "new": "pending_pickup",
            "booked": "pending_pickup",
            "pending pickup": "pending_pickup",
            "in transit": "in_transit",
            "out for delivery": "out_for_delivery",
            "exception": "exception",
            "delivered": "delivered",
            "rto in transit": "rto_in_transit",
            "rto delivered": "rto_delivered",
            "lost": "lost",
            "damaged": "damaged",
            "cancelled": "ready_to_ship",
        }

        internal_status = status_map.get(status)

        if not internal_status:
            logger.warning(f"Jiffy Webhook:: Unknown status: {status}")
            return JsonResponse({"message": "Status ignored (unknown)"})

        # 2️⃣ Fetch order by AWB
        try:
            order = Order.objects.get(
                awb_number=awb, logistic_partner__abbreviation__startswith="jf_"
            )
        except Order.DoesNotExist:
            logger.error(f"Jiffy Webhook:: Order with AWB {awb} not found")
            return JsonResponse({"error": "Order not found"}, status=404)
        except Exception:
            logger.error(f"Jiffy Webhook:: Error fetching order with AWB {awb}", exc_info=True)
            return JsonResponse({"error": "Internal error"}, status=500)

        # 3️⃣ Update order
        previous_status = order.status
        order.update_status(internal_status)

        # Save webhook raw JSON inside order.json for logs
        order.json |= payload
        order.save(update_fields=["status", "json"])

        logger.info(
            f"Jiffy Webhook:: Order #{order.id} ({awb}) updated {previous_status} -> {internal_status}"
        )

        return JsonResponse({"message": "Webhook processed successfully"})

    except Exception:
        logger.error("Jiffy Webhook:: error", exc_info=True)
        return JsonResponse({"error": "Internal error"}, status=500)
