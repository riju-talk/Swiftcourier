import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from order_manager.models import Order


logger = logging.getLogger("my-logger")


# Create your views here.
@csrf_exempt
def rapidshyp_new_webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed, only POST method allowed"}, status=405
        )

    try:
        try:
            data = request.body.decode("utf-8")
        except Exception:
            logger.exception("RapidShyp New Webhook:: Error: ")
            return JsonResponse({"error": "Failed while deecoding request body"}, status=400)

        if not data or data == "":
            return JsonResponse({"error": "Empty payload"}, status=400)

        try:
            payload = json.loads(data)
            logger.debug(f"RapidShyp New Webhook:: payload: {payload}")
        except Exception:
            logger.exception("RapidShyp New Webhook:: Error: ")
            return JsonResponse({"error": "Failed while converting into JSON"}, status=400)

        response = {}
        records = payload.get("records", [])

        for record in records:
            shipment_data = record.get("shipment_details", [])

            for data in shipment_data:
                awb = data.get("awb")
                # status = data.get("shipment_status")
                status = data.get("current_tracking_status_code")

                if not awb or not status:
                    logger.warning(
                        "RapidShyp New Webhook:: Missing awb or current_tracking_status_code in shipment_details"
                    )
                    response["message"] = (
                        "Missing awb or shipment_status in shipment_details"
                    )
                    continue

                # 1️⃣ Map RapidShyp -> Internal Order statuses
                status_map = {
                    "SCB": "pending_pickup",
                    "PSH": "pending_pickup",
                    "OFP": "pending_pickup",
                    "PUE": "pending_pickup",
                    "PUC": "in_transit",
                    "SPD": "in_transit",
                    "INT": "in_transit",
                    "RAD": "in_transit",
                    "DED": "in_transit",
                    "OFD": "out_for_delivery",
                    "DEL": "delivered",
                    "PDL": "delivered",
                    "UND": "ndr",
                    "RTO_REQ": "rto",
                    "RTO": "rto",
                    "RTO_INT": "rto_in_transit",
                    "RTO_RAD": "rto_in_transit",
                    "RTO_OFD": "rto_out_for_delivery",
                    "RTO_DEL": "rto_delivered",
                    "RTO_UND": "rto",
                    "LST": "lost",
                    "DMG": "damaged",
                    "MSR": "in_transit",
                    "DPO": "exception",
                    "MSN": "exception",
                    "RSCB": "rto",
                }

                internal_status = status_map.get(status)

                if not internal_status:
                    logger.warning(
                        f"RapidShyp New Webhook:: Unknown status from RapidShyp: {status}"
                    )
                    response["message"] = "Status ignored (unknown)"
                    continue

                # 2️⃣ Fetch order by AWB
                try:
                    order = Order.objects.get(
                        awb_number=awb,
                        logistic_partner__abbreviation__startswith="rsn_",
                    )
                except Order.DoesNotExist:
                    logger.error(
                        f"RapidShyp New Webhook:: Order with AWB {awb} not found"
                    )
                    response["message"] = "Order not found"
                    continue
                except Exception:
                    logger.error(
                        f"RapidShyp New Webhook:: Error fetching order with AWB {awb}", exc_info=True
                    )
                    response["message"] = "Error fetching order"
                    continue

                # 3️⃣ Update order
                previous_status = order.status
                order.update_status(internal_status)

                # Save webhook raw JSON inside order.json for logs
                order.json |= payload
                order.save(update_fields=["status", "json"])

                logger.info(
                    f"RapidShyp New Webhook:: Order #{order.id} ({awb}) updated {previous_status} -> {internal_status}"
                )

        return JsonResponse(response)
    except Exception:
        logger.exception("RapidShyp New Webhook:: error")
        return JsonResponse({"error": "Internal error"}, status=500)
