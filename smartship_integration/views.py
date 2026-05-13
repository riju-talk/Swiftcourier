import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from order_manager.models import Order


logger = logging.getLogger("my-logger")


# Create your views here.
@csrf_exempt
def webhook(request):
    response = {
        "data": {"message": {"success": True, "description": "No response msg"}}
    }

    if request.method != "POST":
        response["data"]["message"]["success"] = False
        response["data"]["message"]["description"] = "Only POST Request Allowed"
        return JsonResponse(response, status=405)

    try:
        data = request.body.decode("utf-8")
        if not data or data == "":
            response["data"]["message"]["description"] = "Only POST Request Allowed"
            return JsonResponse(response)

        payload = json.loads(data)
        logger.debug(f"Smartship Webhook:: payload: {payload}")

        awb = payload.get("awbno")
        status = payload.get("status")

        if not awb or not status:
            response["data"]["message"]["description"] = "AWB Number Missing"
            return JsonResponse({"error": "tracking_number or status missing"})

        # 1️⃣ Map Smartship -> Internal Order statuses
        status_map = {
            9: "pending_pickup",
            10: "in_transit",
            11: "delivered",
            12: "ndr",
            13: "ndr",
            14: "ndr",
            15: "ndr",
            16: "ndr",
            17: "ndr",
            18: "rto",
            19: "rto",
            22: "ndr",
            23: "ndr",
            24: "pending_pickup",
            # 26: "",
            27: "in_transit",
            28: "rto_in_transit",
            30: "out_for_delivery",
            59: "in_transit",
            # 185: "",
            189: "lost",
            198: "rto",
            207: "in_transit",
            209: "in_transit",
            210: "ndr",
            212: "rto",
            214: "ndr",
            215: "in_transit",
            199: "rto_delivered",
            201: "rto_delivered",
        }

        internal_status = status_map.get(status)

        if not internal_status:
            logger.warning(
                f"Smartship Webhook:: Unknown status from Smartship: {status}"
            )
            response["data"]["message"]["description"] = "Status Ignored"
            return JsonResponse(response)

        # 2️⃣ Fetch order by AWB
        try:
            order = Order.objects.get(
                awb_number=awb, logistic_partner__abbreviation__startswith="ss_"
            )
        except Order.DoesNotExist:
            logger.error(f"Smartship Webhook:: Order with AWB {awb} not found")
            response["data"]["message"]["description"] = "Order not found"
            return JsonResponse(response)
        except Exception as e:
            logger.error(
                f"Smartship Webhook:: Error fetching order with AWB {awb}: {str(e)}"
            )
            response["data"]["message"]["description"] = "Error while fetching details"
            return JsonResponse(response)

        # 3️⃣ Update order
        previous_status = order.status
        order.update_status(internal_status)

        # Save webhook raw JSON inside order.json for logs
        order.json |= payload
        order.save(update_fields=["status", "json"])

        logger.info(
            f"Smartship Webhook:: Order #{order.id} ({awb}) updated {previous_status} -> {internal_status}"
        )

        response["data"]["message"]["description"] = "Webhook processed successfully"
        return JsonResponse(response)

    except Exception as e:
        logger.error(f"Smartship Webhook:: error: {str(e)}")
        response["data"]["message"]["description"] = "Internal server error"
        return JsonResponse(response)
