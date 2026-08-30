import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from order_manager.webhook_events import log_carrier_webhook

from order_manager.models import Order


logger = logging.getLogger("my-logger")


# Create your views here.
@csrf_exempt
@log_carrier_webhook("rapidshyp")
def rapidshyp_webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed, only POST method allowed"}, status=405
        )

    try:
        data = request.body.decode("utf-8")
        if not data or data == "":
            return JsonResponse({"error": "Empty payload"}, status=400)

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            logger.warning(f"RapidShyp Webhook:: Invalid JSON payload: {data!r}")
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        logger.debug(f"RapidShyp Webhook:: payload: {payload}")

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
                        "RapidShyp Webhook:: Missing awb or current_tracking_status_code in shipment_details"
                    )
                    response["message"] = (
                        "Missing awb or shipment_status in shipment_details"
                    )
                    continue

                # 1️⃣ Map RapidShyp -> Internal Order statuses
                status_map = {
                    # "ASSIGNED": "pending_pickup",
                    # "CREATED": "pending_pickup",
                    # "IN_TRANSIT": "in_transit",
                    # "OUT_FOR_DELIVERY": "out_for_delivery",
                    # "PICKUP_ERROR": "pending_pickup",
                    # "PICKUP_SCHEDULED": "pending_pickup",
                    # "REALLOACTION_REQUIRED": "ndr",
                    # "SHIPPED": "in_transit",
                    # "DELIVERED": "delivered",
                    # "RTO_INITIATED": "rto",
                    "SCB": "pending_pickup",
                    "PSH": "pending_pickup",
                    "OFP": "pending_pickup",
                    "PUE": "pending_pickup",
                    # "PCN": "",
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
                    # "CAN": "",
                    # "ONH": "",
                    "LST": "lost",
                    "DMG": "damaged",
                    "MSR": "in_transit",
                    "DPO": "exception",
                    "MSN": "exception",
                    "RSCB": "rto",
                    # "RPSH": "",
                    # "ROFP": "",
                    # "RPUE": "",
                    # "RPCN": "",
                    # "RPUC": "",
                    # "RSPD": "",
                    # "RINT": "",
                    # "RRAD": "",
                    # "RDED": "",
                    # "ROFD": "",
                    # "RDEL": "",
                    # "RUND": "",
                    # "RCAN": "",
                    # "RONH": "",
                    # "RLST": "",
                    # "RDMG": "",
                    # "RMSR": "",
                    # "RMSN": "",
                    # "RDPO": "",
                }

                internal_status = status_map.get(status)

                if not internal_status:
                    logger.warning(
                        f"RapidShyp Webhook:: Unknown status from RapidShyp: {status}"
                    )
                    response["message"] = "Status ignored (unknown)"
                    continue

                # 2️⃣ Fetch order by AWB
                try:
                    order = Order.objects.get(
                        awb_number=awb, logistic_partner__abbreviation__startswith="rs_"
                    )
                except Order.DoesNotExist:
                    logger.error(f"RapidShyp Webhook:: Order with AWB {awb} not found")
                    response["message"] = "Order not found"
                    continue
                except Exception:
                    logger.error(
                        f"RapidShyp Webhook:: Error fetching order with AWB {awb}", exc_info=True
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
                    f"RapidShyp Webhook:: Order #{order.id} ({awb}) updated {previous_status} -> {internal_status}"
                )

        return JsonResponse(response or {"message": "No valid shipment details processed"})
    except Exception:
        logger.error("RapidShyp Webhook:: error", exc_info=True)
        return JsonResponse({"error": "Internal error"}, status=500)
