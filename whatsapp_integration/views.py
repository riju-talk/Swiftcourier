import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import WhatsAppNotificationLog


logger = logging.getLogger("my-logger")


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    payload = {}
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = request.POST.dict()

    message_id = payload.get("MessageSid") or payload.get("message_id")
    status = payload.get("MessageStatus") or payload.get("status")

    if not message_id:
        return JsonResponse({"error": "Missing message id"}, status=400)

    log = WhatsAppNotificationLog.objects.filter(
        provider_message_id=message_id
    ).first()
    if not log:
        return JsonResponse({"message": "Log not found"}, status=404)

    if status:
        normalized = status.lower()
        if normalized in {"queued", "sent", "delivered", "failed", "undelivered"}:
            log.delivery_status = normalized

    existing = log.api_response or {}
    existing["webhook"] = payload
    log.api_response = existing
    log.save(update_fields=["delivery_status", "api_response", "updated_at"])

    return JsonResponse({"message": "Webhook processed"}, status=200)
