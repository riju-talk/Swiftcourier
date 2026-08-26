import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


logger = logging.getLogger("my-logger")


# Create your views here.
@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed, only POST method allowed"}, status=405
        )

    try:
        # TODO: Zippyy's webhook status-mapping isn't implemented yet - this
        # only logs the raw payload so a real payload can be captured from
        # the logs the first time Zippyy actually calls in.
        logger.debug(f"Zippyy Webhook:: payload: {request.body!r}")
        return JsonResponse({"message": "Zippyy Webhook:: received successfully"})
    except Exception:
        logger.error("Zippyy Webhook:: error", exc_info=True)
        return JsonResponse({"error": "Internal error"}, status=500)
