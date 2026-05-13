from django.http import JsonResponse


# Create your views here.
def webhook(request):
    return JsonResponse(
        {
            "msg": "Hi",
        }
    )
