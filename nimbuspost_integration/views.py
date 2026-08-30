import base64
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from order_manager.webhook_events import log_carrier_webhook

from account.models import Courier
from order_manager.models import Order

from .constants import AWB_FIELD, STATUS_FIELD, STATUS_MAPPING


logger = logging.getLogger("my-logger")


@csrf_exempt
@log_carrier_webhook("nimbuspost")
def webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed, only POST method allowed"}, status=405
        )

    try:
        raw_body = request.body

        # NimbusPost signs with a base64-encoded X-Hmac-Sha256 header, HMAC-SHA256
        # of the raw body using the Secret configured on the webhook in their
        # dashboard. They only sign if a secret was configured on their side, so
        # this only enforces it if we've configured one on ours too.
        if settings.NIMBUSPOST_WEBHOOK_SECRET:
            received_signature = request.headers.get("X-Hmac-Sha256")
            if not received_signature:
                logger.warning("NimbusPost Webhook:: Missing X-Hmac-Sha256 header")
                return JsonResponse({"error": "Missing signature"}, status=401)

            computed_signature = base64.b64encode(
                hmac.new(
                    settings.NIMBUSPOST_WEBHOOK_SECRET.encode("utf-8"),
                    raw_body,
                    hashlib.sha256,
                ).digest()
            ).decode()

            if not hmac.compare_digest(computed_signature, received_signature):
                logger.warning("NimbusPost Webhook:: Invalid signature")
                return JsonResponse({"error": "Invalid signature"}, status=401)

        if not raw_body:
            return JsonResponse({"error": "Empty payload"}, status=400)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning(f"NimbusPost Webhook:: Invalid JSON payload: {raw_body!r}")
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        logger.debug(f"NimbusPost Webhook:: payload: {payload}")

        awb = payload.get(AWB_FIELD)
        status = payload.get(STATUS_FIELD)

        if not awb or not status:
            logger.warning(
                f"NimbusPost Webhook:: Missing {AWB_FIELD} or {STATUS_FIELD} in payload: {payload}"
            )
            return JsonResponse({"error": "awb_number or status missing"}, status=400)

        internal_status = STATUS_MAPPING.get(status)
        if not internal_status:
            logger.warning(
                f"NimbusPost Webhook:: Unknown/unmapped status from NimbusPost: {status!r} "
                f"(awb_number={awb!r}) - add it to STATUS_MAPPING in constants.py"
            )
            return JsonResponse({"message": "Status ignored (unknown)"})

        try:
            order = Order.objects.get(
                awb_number=awb,
                logistic_partner=Courier.objects.filter(abbreviation="nimbuspost").first(),
            )
        except Order.DoesNotExist:
            logger.error(f"NimbusPost Webhook:: Order with AWB {awb} not found")
            return JsonResponse({"error": "Order not found"}, status=404)
        except Exception:
            logger.error(
                f"NimbusPost Webhook:: Error fetching order with AWB {awb}", exc_info=True
            )
            return JsonResponse({"error": "Internal error"}, status=500)

        previous_status = order.status
        order.update_status(internal_status)
        order.json |= payload
        order.save(update_fields=["status", "json"])

        logger.info(
            f"NimbusPost Webhook:: Order #{order.id} ({awb}) updated {previous_status} -> "
            f"{internal_status} ({payload.get('message', '')} @ {payload.get('location', '')})"
        )

        return JsonResponse({"message": "Webhook processed successfully"})

    except Exception:
        logger.error("NimbusPost Webhook:: error", exc_info=True)
        return JsonResponse({"error": "Internal error"}, status=500)
