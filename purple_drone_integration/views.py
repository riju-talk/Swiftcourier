import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from order_manager.webhook_events import log_carrier_webhook

from order_manager.models import Order


logger = logging.getLogger("my-logger")


@csrf_exempt
@log_carrier_webhook("purple_drone")
def webhook(request):
    try:
        raw_body = request.body.decode("utf-8")
        if not raw_body:
            logger.error(f"Empty webhook body received, body: {raw_body}")
            return JsonResponse({"error": "Empty body"}, status=400)
        
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {raw_body}")
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        logger.debug(f"PurpleDrone Webhook payload: {payload}")

        data = payload.get("data", {})
        awb = data.get("tracking_number")
        status = data.get("status")

        if not awb or not status:
            return JsonResponse({"error": "tracking_number or status missing"}, status=400)

        # 1️⃣ Map PurpleDrone -> Internal Order statuses
        # NOTE: this used to be two separate `status_map` dicts defined back
        # to back, so the human-readable entries below (from an earlier
        # webhook format) were dead code, silently shadowed by the
        # O-*/RTO-* dict that followed. Merged into one so either format is
        # still recognized instead of every one of these being classified
        # "unknown" and ignored.
        status_map = {
            "Cancelled": "cancelled",
            "Confirmation": "pending_pickup",
            "Pickup Not Attempted/Failed": "pending_pickup",
            "Out For Pickup": "pending_pickup",
            "Intransit": "in_transit",
            "Delivered": "delivered",
            "Undelivered": "ndr",
            "Return Initiated": "rto",
            "RTO in Transit": "rto_in_transit",
            "RTO delivered": "rto_delivered",
            "Shipment Lost": "lost",
            "O-CREATED": "pending_pickup",
            "O-CONFIRMED": "pending_pickup",
            "O-TRKID-GENERATED": "pending_pickup",
            "O-MANIFEST": "pending_pickup",
            "SMS-NOTIFICATION": "pending_pickup",
            "WHATSAPP-NOTIFICATION": "pending_pickup",
            "O-CANCELLED": "ready_to_ship",
            "O-PENDING-IN-WH": "pending_pickup",
            "O-QC-IN-WH": "pending_pickup",
            "O-WAITING-FOR-PICKUP": "pending_pickup",
            "O-PICKEDUP": "in_transit",
            "O-OUT-FOR-PICKUP": "pending_pickup",
            "O-PICKUP-FAILED": "pending_pickup",
            "O-LOST": "lost",
            "O-INTRANSIT": "in_transit",
            "O-REACHED-AT-DEST": "in_transit",
            "O-OUTFORDELIVERY": "out_for_delivery",
            "RTO": "rto",
            "RTO-OUT-FOR-PICKUP": "rto_pending_pickup",
            "RTO-INTRANSIT": "rto_in_transit",
            "RTO-OFD": "rto_out_for_delivery",
            "RTO-REACHED-WH": "rto_in_transit",
            "RTO-DELIVERED": "rto_delivered",
            "UNDELIVERED": "ndr",
            "ESCALATE_REQUESTED": "ndr",
            "RTO_REQUESTED": "rto",
            "REATTEMPT_REQUESTED": "ndr",
            "O-HOLD": "ndr",
            "O-DELIVERED": "delivered",
        }

        internal_status = status_map.get(status)

        if not internal_status:
            logger.warning(f"Unknown status from PurpleDrone: {status}")
            return JsonResponse({"message": "Status ignored (unknown)"})

        # 2️⃣ Fetch order by AWB
        try:
            order = Order.objects.get(awb_number=awb, logistic_partner__abbreviation__startswith="pd")
        except Order.DoesNotExist:
            logger.error(f"Order with AWB {awb} not found")
            return JsonResponse({"error": "Order not found"}, status=404)
        except Exception:
            logger.error(f"Error fetching order with AWB {awb}", exc_info=True)
            return JsonResponse({"error": "Internal error"}, status=500)

        # 3️⃣ Update order
        previous_status = order.status
        order.update_status(internal_status)

        # Save webhook raw JSON inside order.json for logs
        order.json |= payload
        order.save(update_fields=["status", "json"])

        logger.info(
            f"Order #{order.id} ({awb}) updated {previous_status} -> {internal_status}"
        )

        return JsonResponse({"message": "Webhook processed successfully"})

    except Exception:
        logger.error("PurpleDrone Webhook error", exc_info=True)
        return JsonResponse({"error": "Internal error"}, status=500)
