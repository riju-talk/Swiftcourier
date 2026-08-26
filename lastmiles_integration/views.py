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
        # TODO: Lastmiles has never sent us a real webhook payload to model
        # this against, so status-mapping isn't implemented yet - this just
        # acknowledges receipt and logs the raw body so a real payload can be
        # captured from the logs the first time Lastmiles actually calls in.
        logger.info(f"Lastmiles Webhook:: payload: {request.body!r}")
        return JsonResponse({"message": "Webhook received"})
    except Exception:
        logger.error("Lastmiles Webhook:: error", exc_info=True)
        return JsonResponse({"error": "Internal error"}, status=500)
