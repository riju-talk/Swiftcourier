import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


logger = logging.getLogger("my-logger")


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed, only POST method allowed"}, status=405
        )

    try:
        # TODO: BDL's webhook status-mapping isn't implemented yet - this
        # previously ignored the request body entirely. Now it at least logs
        # the raw payload so a real payload can be captured from the logs.
        logger.info(f"BDL Webhook:: payload: {request.body!r}")
        return JsonResponse({"msg": "Webhook received"})
    except Exception:
        logger.error("BDL Webhook:: error", exc_info=True)
        return JsonResponse({"error": "Internal error"}, status=500)
