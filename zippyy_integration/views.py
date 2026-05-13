import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


logger = logging.getLogger("my-logger")


# Create your views here.
@csrf_exempt
def webhook(request):
    logger.debug(f"Zippyy Webhook:: payload: {request.body}")
    return JsonResponse({"message": "Zippyy Webhook:: received successfully"})
