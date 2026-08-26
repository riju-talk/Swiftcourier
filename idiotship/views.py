import logging
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from account.models import ContactUs, SubscribeNewsletter, User
from order_manager.models import Order

logger = logging.getLogger("my-logger")


def index(request):
    if request.user.is_anonymous:
        return redirect("account:signin")

    if request.user.role == User.SUPER_ADMIN:
        return redirect("superadmin_panel:dashboard")

    if request.user.role == User.ADMIN:
        return redirect("admin_panel:dashboard")

    if request.user.role == User.USER:
        return redirect("user_panel:dashboard")

    # role is unset/unrecognized (e.g. a superuser created without a role) —
    # fall back rather than returning None, which Django would treat as a crash.
    return redirect("account:signin")


def track_shipment(request):
    if request.method != "GET":
        return HttpResponse("Method not allowed", status=405)

    awb_number = request.GET.get("awb_number")
    if not awb_number:
        return render(request, "track_shipment.dj")

    order = (
        Order.objects.filter(awb_number=awb_number).select_related("shipment").first()
    )

    ctx = {
        "valid_order": bool(order),
        "awb_number": awb_number,
        "past_timeline": [],
        "current_timeline": [],
        "future_timeline": [],
    }

    if not order:
        return render(request, "track_shipment.dj", ctx)

    # ================= BASE FLOWS =================
    base_flow = [
        "ready_to_ship",
        "pending_pickup",
        "in_transit",
        "out_for_delivery",
        "delivered",
    ]

    exception_flow = [
        "ndr",
        "exception",
        "lost",
        "damaged",
        "cancelled",
    ]

    rto_exception_flow = [
        "rto_cancelled",
        "rto_lost",
        "rto_damaged",
    ]

    # ================= DYNAMIC FLOW =================
    flow = base_flow.copy()

    # --- Forward exceptions ---
    if order.status in exception_flow:
        flow.append(order.status)

    # --- RTO flow ---
    if order.status.startswith("rto"):
        flow.extend(
            [
                "rto",
                "rto_pending_pickup",
                "rto_in_transit",
                "rto_out_for_delivery",
                "rto_delivered",
            ]
        )

        if order.status in rto_exception_flow:
            flow.append(order.status)

    # Remove duplicates while preserving order
    flow = list(dict.fromkeys(flow))

    # ================= CURRENT INDEX =================
    try:
        current_index = flow.index(order.status)
    except ValueError:
        current_index = 0

    shipment = getattr(order, "shipment", None)

    # ================= STATUS → TIMESTAMP =================
    status_time_map = {
        "ready_to_ship": order.created_at,
        "pending_pickup": getattr(shipment, "booked_at", None),
        "in_transit": getattr(shipment, "shipped_at", None),
        "out_for_delivery": getattr(shipment, "out_for_delivery_at", None),
        "delivered": getattr(shipment, "delivered_at", None),
        "ndr": getattr(shipment, "ndr_at", None),
        "exception": getattr(shipment, "exception_at", None),
        "lost": getattr(shipment, "lost_at", None),
        "damaged": getattr(shipment, "damaged_at", None),
        "cancelled": order.order_date,
        "rto": getattr(shipment, "rto_at", None),
        "rto_pending_pickup": getattr(shipment, "rto_booked_at", None),
        "rto_in_transit": getattr(shipment, "rto_shipped_at", None),
        "rto_out_for_delivery": getattr(shipment, "rto_out_for_delivery_at", None),
        "rto_delivered": getattr(shipment, "rto_delivered_at", None),
        "rto_cancelled": getattr(shipment, "rto_cancelled_at", None),
        "rto_lost": getattr(shipment, "rto_lost_at", None),
        "rto_damaged": getattr(shipment, "rto_damaged_at", None),
    }

    # ================= BUILD TIMELINES =================
    for index, status in enumerate(flow):
        label = Order.ORDER_MAPPING.get(status, status.replace("_", " ").title())
        timestamp = status_time_map.get(status)

        if index < current_index:
            ctx["past_timeline"].append((label, timestamp))
        elif index == current_index:
            ctx["current_timeline"].append((label, timestamp))
        else:
            ctx["future_timeline"].append((label, None))

    # ================= TERMINAL STATES =================
    if order.status in [
        "delivered",
        "cancelled",
        "lost",
        "damaged",
        "rto_delivered",
        "rto_lost",
        "rto_damaged",
        "rto_cancelled",
    ]:
        ctx["future_timeline"] = []

    return render(request, "track_shipment.dj", ctx)


def subscribe_newsletter(request):
    if request.method == "GET":
        email = request.GET.get("email")
        if email:
            SubscribeNewsletter.subscribe(email)
            return JsonResponse({"message": "Subscribed"})
        else:
            return JsonResponse({"message": "Email Required"})

    return JsonResponse({"message": "Invalid Request Method"})


@csrf_exempt
def contact_us(request):
    if request.method == "POST":
        data = request.POST
        _name = data.get("name", "").strip()
        _contact_no = data.get("contact_no", "").strip()
        _subject = data.get("subject", "").strip()
        _message = data.get("message", "").strip()
        _courier_type = data.get("courier_type", "").strip()
        _is_request_a_quote = data.get("is_request_a_quote", "").strip()

        if not (10 <= len(_contact_no) <= 15):
            return JsonResponse({"message": "Invalid Contact No"})

        if _is_request_a_quote:
            ContactUs.add_get_a_quote(
                name=_name,
                contact_no=_contact_no,
                subject=_subject,
                message=_message,
                courier_type=_courier_type,
            )
        else:
            ContactUs.add_contact_us_request(
                name=_name,
                contact_no=_contact_no,
                subject=_subject,
                message=_message,
            )

        return JsonResponse({"message": "Form submitted"})

    return JsonResponse({"message": "Invalid Request Method"})


def custom_404(request, exception):
    return render(request, "404.dj", status=404)


def custom_500(request):
    return render(request, "500.dj", status=500)
