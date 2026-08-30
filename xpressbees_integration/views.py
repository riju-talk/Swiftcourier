import hmac
import hashlib
import base64
import json
import logging

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from order_manager.webhook_events import log_carrier_webhook
from django.http import HttpResponse, JsonResponse

from account.models import Courier

from .constants import STATUS_MAPPING
from order_manager.models import Order


logger = logging.getLogger("my-logger")


@csrf_exempt
@log_carrier_webhook("xpressbees")
def webhook(request):
    if request.method != "POST":
        logger.debug(f"XpressBees Webhook:: Invalid request method: {request.method}")
        return HttpResponse("Invalid method", status=405)

    try:
        # Read raw body
        raw_data = request.body
        received_signature = request.headers.get("X-Hmac-Sha256")

        # Conditional HMAC verification
        if settings.SECRET_KEY:  # Configure this in settings.py
            if not received_signature:
                logger.debug("XpressBees Webhook:: Missing HMAC header")
                return HttpResponse("Missing HMAC header", status=401)

            secret_bytes = settings.SECRET_KEY.encode("utf-8")
            computed_hash = base64.b64encode(
                hmac.new(secret_bytes, raw_data, hashlib.sha256).digest()
            ).decode()

            if not hmac.compare_digest(computed_hash, received_signature):
                logger.debug("XpressBees Webhook:: Invalid signature")
                return HttpResponse("Invalid signature", status=401)

        # Parse JSON
        try:
            data = json.loads(raw_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning(f"XpressBees Webhook:: Invalid JSON body: {raw_data!r}")
            return HttpResponse("Invalid JSON", status=400)
        data_debug = str(data)

        # Extract status (using correct field name)
        status_str = data.get("status_code")
        if not status_str:
            logger.debug(f"XpressBees Webhook:: Missing status. DATA: {data_debug}")
            return HttpResponse("Missing status", status=400)

        # Validate and update status
        if status_str not in STATUS_MAPPING:  # Use key existence check
            logger.debug(f"XpressBees Webhook:: Invalid status. DATA: {data_debug}")
            return HttpResponse("Invalid status", status=400)

        # Validate required fields
        if "awb_number" not in data:
            logger.debug(f"XpressBees Webhook:: Missing awb_number. DATA: {data_debug}")
            return HttpResponse("Missing awb_number", status=400)

        # Fetch order
        order = Order.objects.filter(
            logistic_partner=Courier.objects.filter(abbreviation="xb").first(), awb_number=data["awb_number"]
        ).first()
        if not order:
            logger.debug(f"XpressBees Webhook:: Order not found. DATA: {data_debug}")
            return HttpResponse("Order not found", status=404)

        order.update_status(STATUS_MAPPING[status_str])
        order.save()

        logger.debug(f"XpressBees Webhook:: Webhook processed. DATA: {data_debug}")

        return JsonResponse({"status": "success"})

    except Exception:
        logger.error("XpressBees Webhook:: Webhook error", exc_info=True)
        return HttpResponse("Error processing webhook", status=500)
