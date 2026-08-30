# Django imports
from datetime import datetime, timedelta
import traceback
import uuid

from django.utils import timezone
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Avg, F, ExpressionWrapper, DurationField

# Local app imports
from account.decorators import superadmin_required
from account.models import (
    Activity,
    BlockedPincode,
    Courier,
    Notification,
    RateCard,
    User,
)
from order_manager.models import Order
from wallet.models import Transaction


# Create your views here.


@superadmin_required
def statistics(request):
    response = {
        "revenue": {
            "total_profit": 354,
            "labels": [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ],
            "series": [
                {
                    "name": "Income",
                    "data": [
                        60000,
                        12000,
                        25000,
                        15000,
                        20000,
                        17000,
                        55000,
                        30000,
                        40000,
                        35000,
                        45000,
                        50000,
                    ],
                },
                {
                    "name": "Expenses",
                    "data": [
                        9000,
                        8000,
                        11000,
                        19000,
                        10000,
                        15000,
                        13000,
                        14000,
                        12000,
                        18000,
                        17000,
                        16000,
                    ],
                },
            ],
        },
        "sales_by_category": {
            "labels": [
                "xpressbee",
                "bluedart",
            ],
            "series": [50, 178],
        },
        # sales means total amount in inr
        "daily_sales": {
            "labels": ["Sun", "Mon", "Tue", "Wed", "Thur", "Fri", "Sat"],
            "series": [
                {"name": "Sales", "data": [66, 55, 41, 67, 22, 43, 21]},
                {"name": "Last Week", "data": [13, 23, 20, 8, 13, 27, 33]},
            ],
        },
        "total_orders": {
            "total": 312,
            "series": [
                {"name": "Sales", "data": [28, 40, 36, 52, 38, 60, 38, 52, 36, 40]}
            ],
        },
        "summary": {
            "income": 60000,
            "profit": 25000,
            "expenses": 9000,
            "income_percent": 92,
            "profit_percent": 65,
            "expenses_percent": 80,
        },
        "recent_orders": [
            {
                "image": "/media/default/user_logo.png",
                "name": "User Name",
                "product_name": "Order 1",
                "price": "1000",
                "status": "Delivered",
            },
            {
                "image": "/media/default/user_logo.png",
                "name": "User Name 2",
                "product_name": "Order 2",
                "price": "2000",
                "status": "Shipping",
            },
        ],
    }
    return JsonResponse(response)


@superadmin_required
def dashboard(request):
    if request.GET.get("data", "false") == "true":

        # Base queryset (exclude non-active orders)
        order_queryset = Order.objects.exclude(
            status__in=["cancelled", "ready_to_ship"]
        )

        today = timezone.localdate()

        # ---- DATETIME HELPERS (MIDNIGHT SAFE) ----
        def start_of_day(date):
            return timezone.make_aware(datetime.combine(date, datetime.min.time()))

        def end_of_day(date):
            return timezone.make_aware(datetime.combine(date, datetime.max.time()))

        # ---- PRIMARY KPIs ----
        today_start = start_of_day(today)
        yesterday = today - timedelta(days=1)
        last_7_days_start = start_of_day(today - timedelta(days=6))
        last_30_days_start = start_of_day(today - timedelta(days=29))

        today_orders = order_queryset.filter(
            shipment__booked_at__gte=today_start
        ).count()

        yesterday_orders = order_queryset.filter(
            shipment__booked_at__range=(
                start_of_day(yesterday),
                end_of_day(yesterday),
            )
        ).count()

        last_7_days_orders = order_queryset.filter(
            shipment__booked_at__gte=last_7_days_start
        ).count()

        last_30_days_orders = order_queryset.filter(
            shipment__booked_at__gte=last_30_days_start
        ).count()

        # ---- SECONDARY KPIs ----
        month_start = start_of_day(today.replace(day=1))
        prev_month_last_day = month_start - timedelta(days=1)
        prev_month_start = start_of_day(prev_month_last_day.replace(day=1))

        year_start = start_of_day(today.replace(month=1, day=1))

        this_month_orders = order_queryset.filter(
            shipment__booked_at__gte=month_start
        ).count()

        prev_month_orders = order_queryset.filter(
            shipment__booked_at__range=(
                prev_month_start,
                end_of_day(prev_month_last_day),
            )
        ).count()

        this_year_orders = order_queryset.filter(
            shipment__booked_at__gte=year_start
        ).count()

        # ---- COURIER PERFORMANCE (SAMPLE LOGIC) ----
        courier_performance = order_queryset.values("logistic_partner__name").annotate(
            total=Count("id", filter=~Q(status__in=["cancelled", "ready_to_ship"])),
            delivered=Count("id", filter=Q(status="delivered")),
        )

        courier_data = {}
        for row in courier_performance:
            courier = row["logistic_partner__name"] or "Unknown"
            total = row["total"]
            delivered = row["delivered"]
            courier_data[courier.lower()] = (
                round((delivered / total) * 100, 2) if total else 0
            )

        # ---- ALERTS ----
        high_ndr_rate = order_queryset.filter(status="ndr").count()

        pickup_delays = order_queryset.filter(status="pending_pickup").count()

        courier_exceptions = order_queryset.filter(status="exception").count()

        return JsonResponse(
            {
                # ---- PRIMARY KPIs ----
                "todaySoFar": today_orders,
                "yesterdayOrders": yesterday_orders,
                "last_7_days": last_7_days_orders,
                "last_30_days_orders": last_30_days_orders,
                # ---- SECONDARY KPIs ----
                "thisMonthOrders": this_month_orders,
                "prevMonthOrders": prev_month_orders,
                "thisYearOrders": this_year_orders,
                # ---- COURIER PERFORMANCE ----
                "courier_performance": courier_data,
                # ---- ALERTS ----
                "attention_required": {
                    "high_ndr_rate": high_ndr_rate,
                    "pickup_delays": pickup_delays,
                    "courier_exceptions": courier_exceptions,
                },
            }
        )

    return render(request, "superadmin_panel/dashboard/overview.dj")


@superadmin_required
def dashboard_client(request):
    if request.GET.get("data", "false") == "true":
        today = timezone.localdate()

        base_qs = Order.objects.exclude(status__in=["cancelled", "ready_to_ship"])

        # -------------------------------
        # PRIMARY KPIs
        # -------------------------------
        total_orders = base_qs.count()

        pending_pickup = base_qs.filter(status="pending_pickup").count()
        in_transit = base_qs.filter(status="in_transit").count()
        delivered = base_qs.filter(status="delivered").count()
        rto_orders = base_qs.filter(status__startswith="rto").count()
        ndr_orders = base_qs.filter(status="ndr").count()
        cancelled = Order.objects.filter(status="cancelled").count()

        # -------------------------------
        # CLIENT METRICS
        # -------------------------------
        active_clients = User.objects.filter(is_active=True).count()

        clients_with_live_orders = (
            User.objects.filter(orders__status__in=["pending_pickup", "in_transit"])
            .distinct()
            .count()
        )

        new_clients_last_30_days = User.objects.filter(
            created_at__gte=timezone.make_aware(
                datetime.combine(today - timedelta(days=30), datetime.min.time())
            ),
            role=User.USER,
        ).count()

        # -------------------------------
        # COURIER PERFORMANCE (client side)
        # -------------------------------
        courier_performance_qs = base_qs.values("logistic_partner__name").annotate(
            total=Count("id"),
            delivered=Count("id", filter=Q(status="delivered")),
        )

        courier_performance = {}
        for row in courier_performance_qs:
            if row["total"] > 0:
                courier_performance[row["logistic_partner__name"]] = round(
                    (row["delivered"] / row["total"]) * 100, 2
                )

        # -------------------------------
        # RISK INDICATORS
        # -------------------------------
        high_rto_clients = (
            base_qs.filter(status="rto")
            .values("user__id")
            .annotate(cnt=Count("id"))
            .filter(cnt__gte=10)
            .count()
        )

        high_ndr_clients = (
            base_qs.filter(status="ndr")
            .values("user__id")
            .annotate(cnt=Count("id"))
            .filter(cnt__gte=10)
            .count()
        )

        sla_breach_clients = 0

        # -------------------------------
        # CLIENT-WISE SHIPMENTS TABLE
        # -------------------------------
        client_shipments_qs = (
            base_qs.values("user__full_name", "user__email")
            .annotate(
                total=Count("id"),
                pending=Count("id", filter=Q(status="pending_pickup")),
                in_transit=Count("id", filter=Q(status="in_transit")),
                delivered=Count("id", filter=Q(status="delivered")),
                rto=Count("id", filter=Q(status="rto")),
                ndr=Count("id", filter=Q(status="ndr")),
            )
            .order_by("-total")
        )

        client_shipments = {}
        for row in client_shipments_qs:
            client_shipments[f'{row["user__full_name"]} ({row["user__email"]})'] = {
                "total": row["total"],
                "pending": row["pending"],
                "in_transit": row["in_transit"],
                "delivered": row["delivered"],
                "rto": row["rto"],
                "ndr": row["ndr"],
            }

        return JsonResponse(
            {
                # ---- ORDER KPIs ----
                "total_orders": total_orders,
                "pending_pickup": pending_pickup,
                "in_transit": in_transit,
                "delivered": delivered,
                "rto_orders": rto_orders,
                "ndr_orders": ndr_orders,
                "cancelled": cancelled,
                # ---- CLIENT METRICS ----
                "client_metrices": {
                    "active": active_clients,
                    "with_live_orders": clients_with_live_orders,
                    "new_last_30_days": new_clients_last_30_days,
                },
                # ---- COURIER PERFORMANCE ----
                "courier_performance": courier_performance,
                # ---- RISK INDICATORS ----
                "risk_indicator": {
                    "high_rto_clients": high_rto_clients,
                    "high_ndr_clients": high_ndr_clients,
                    "sla_breach": sla_breach_clients,
                },
                # ---- CLIENT SHIPMENTS TABLE ----
                "client_shipments": client_shipments,
            }
        )

    return render(request, "superadmin_panel/dashboard/client.dj")


@superadmin_required
def dashboard_courier_partner(request):
    if request.GET.get("data", "false") == "true":
        base_qs = Order.objects.exclude(status__in=["cancelled", "ready_to_ship"])

        courier_qs = (
            base_qs.values("logistic_partner__name")
            .annotate(
                total_orders=Count("id"),
                pending_pickup=Count("id", filter=Q(status="pending_pickup")),
                in_transit=Count("id", filter=Q(status="in_transit")),
                delivered=Count("id", filter=Q(status="delivered")),
                rto=Count("id", filter=Q(status__startswith="rto")),
                ndr=Count("id", filter=Q(status="ndr")),
            )
            .order_by("-total_orders")
        )

        response = {}

        for row in courier_qs:
            total = row["total_orders"] or 0
            delivered = row["delivered"] or 0

            response[row["logistic_partner__name"].lower()] = {
                "pending_pickup": row["pending_pickup"],
                "in_transit": row["in_transit"],
                "delivered": delivered,
                "rto": row["rto"],
                "ndr": row["ndr"],
                "delivery_perc": round((delivered / total) * 100, 2) if total else 0,
                "total_orders": total,
            }

        return JsonResponse(response)

    return render(request, "superadmin_panel/dashboard/courier_partner.dj")


@superadmin_required
def dashboard_courier_performance(request):
    if request.GET.get("data", "false") == "true":

        base_qs = Order.objects.exclude(status__in=["cancelled", "ready_to_ship"])

        # ---------- PER COURIER METRICS ----------
        courier_qs = base_qs.values("logistic_partner__name").annotate(
            total=Count("id"),
            delivered=Count("id", filter=Q(status="delivered")),
            rto=Count("id", filter=Q(status__startswith="rto")),
            ndr=Count("id", filter=Q(status="ndr")),
            # TATs (Duration)
            pickup_tat=Avg(
                ExpressionWrapper(
                    F("shipment__shipped_at") - F("shipment__booked_at"),
                    output_field=DurationField(),
                )
            ),
            delivery_tat=Avg(
                ExpressionWrapper(
                    F("shipment__delivered_at") - F("shipment__shipped_at"),
                    output_field=DurationField(),
                )
            ),
            rto_tat=Avg(
                ExpressionWrapper(
                    F("shipment__delivered_at") - F("shipment__shipped_at"),
                    output_field=DurationField(),
                )
            ),
        )

        courier_partners = {}
        delivery_perc_list = []
        pickup_tat_list = []
        delivery_tat_list = []
        rto_tat_list = []

        for row in courier_qs:
            total = row["total"] or 0
            delivered = row["delivered"] or 0
            rto = row["rto"] or 0
            ndr = row["ndr"] or 0

            delivery_perc = round((delivered / total) * 100, 2) if total else 0
            rto_perc = round((rto / total) * 100, 2) if total else 0
            ndr_perc = round((ndr / total) * 100, 2) if total else 0

            # Convert timedelta → days
            pickup_tat = round(
                (row["pickup_tat"].total_seconds() / 86400) if row["pickup_tat"] else 0,
                2,
            )
            delivery_tat = round(
                (
                    (row["delivery_tat"].total_seconds() / 86400)
                    if row["delivery_tat"]
                    else 0
                ),
                2,
            )
            rto_tat = round(
                (row["rto_tat"].total_seconds() / 86400) if row["rto_tat"] else 0,
                2,
            )

            # SLA logic
            if delivery_perc >= 90 and rto_perc <= 7:
                sla_status = "Good"
            elif delivery_perc >= 80 and rto_perc <= 10:
                sla_status = "Watch"
            else:
                sla_status = "Risk"

            courier_partners[row["logistic_partner__name"].lower()] = {
                "delivery_perc": delivery_perc,
                "pickup_tat": pickup_tat,
                "delivery_tat": delivery_tat,
                "rto_perc": rto_perc,
                "ndr_perc": ndr_perc,
                "sla_status": sla_status,
            }

            delivery_perc_list.append(delivery_perc)
            pickup_tat_list.append(pickup_tat)
            delivery_tat_list.append(delivery_tat)
            rto_tat_list.append(rto_tat)

        # ---------- AVERAGES ----------
        def avg(lst):
            return round(sum(lst) / len(lst), 2) if lst else 0

        return JsonResponse(
            {
                "avg_delivery_success": avg(delivery_perc_list),
                "avg_pickup_tat": avg(pickup_tat_list),
                "avg_delivery_tat": avg(delivery_tat_list),
                "avg_rto_tat": avg(rto_tat_list),
                "courier_partners": courier_partners,
            }
        )

    return render(
        request,
        "superadmin_panel/dashboard/courier_performance.dj",
    )


@superadmin_required
def dashboard_data(request):
    data = request.GET

    order_queryset = Order.objects.all()
    date_filter = data.get("date_filter", "this_month")
    if date_filter not in ["this_month", "last_month", "this_year"]:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid date_filter value",
                "data": {},
            }
        )

    now_dt = timezone.now()
    if date_filter == "this_month":
        start = now_dt.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        order_queryset = order_queryset.filter(order_date__gte=start)
    elif date_filter == "last_month":
        first_of_this_month = now_dt.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        last_month_end = first_of_this_month - timedelta(microseconds=1)
        start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        order_queryset = order_queryset.filter(
            order_date__gte=start, order_date__lte=last_month_end
        )
    elif date_filter == "this_year":
        start = now_dt.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        order_queryset = order_queryset.filter(order_date__gte=start)

    tab = data.get("tab", "overview")
    if tab == "overview":
        # Return overview data
        return JsonResponse(
            {
                "success": True,
                "data": {
                    "total_orders": order_queryset.count(),
                    "total_pickup_order": order_queryset.filter(
                        status="pending_pickup"
                    ).count(),
                    "total_in_transit_order": order_queryset.filter(
                        status="in_transit"
                    ).count(),
                    "total_delivered_order": order_queryset.filter(
                        status="delivered"
                    ).count(),
                    "total_ndr_order": order_queryset.filter(status="ndr").count(),
                    "total_rto_order": order_queryset.filter(
                        status__startswith="rto"
                    ).count(),
                },
            }
        )
    elif tab == "clients":
        # Return users data
        return JsonResponse(
            {
                "success": True,
                "data": {
                    "total_shipment": order_queryset.count(),
                    "booked": order_queryset.filter(status="ready_to_ship").count(),
                    "pending_pickup": order_queryset.filter(
                        status="pending_pickup"
                    ).count(),
                    "in_transit": order_queryset.filter(status="in_transit").count(),
                    "delivered": order_queryset.filter(status="delivered").count(),
                    "rto": order_queryset.filter(status__startswith="rto").count(),
                    "ndr": order_queryset.filter(status="ndr").count(),
                    "clients": [
                        "S_no",
                        "client_name",
                        "total_shipment",
                        "booked",
                        "pickup",
                        "in_transit",
                        "delivered",
                        "rto",
                        "ndr",
                    ],
                },
            }
        )
    elif tab == "courier_partner":
        # Return transactions data
        return JsonResponse(
            {
                "success": True,
                "data": {},
            }
        )
    elif tab == "courier_performance":
        # Return courier performance data
        return JsonResponse(
            {
                "success": True,
                "data": {},
            }
        )
    else:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid tab value",
                "data": {},
            }
        )


@superadmin_required
def add_admin(request):
    return render(request, "superadmin_panel/add_admin.dj")


@superadmin_required
def list_admin(request):
    admins = User.objects.filter(role=User.ADMIN)
    return render(request, "superadmin_panel/all_admin.dj", {"admins": admins})


@superadmin_required
def api_integration(request):
    return render(request, "superadmin_panel/api_integration.dj")


@superadmin_required
def all_clients(request):
    clients = User.objects.filter(role=User.USER)
    return render(request, "superadmin_panel/all_clients.dj", {"clients": clients})


@superadmin_required
def change_client_status(request, client_id):
    client = get_object_or_404(User, id=client_id, role=User.USER)
    if client.is_active:
        client.is_active = False
        messages.success(request, f"Client {client.full_name} has been deactivated.")
    else:
        client.is_active = True
        messages.success(request, f"Client {client.full_name} has been activated.")
    client.save()

    return redirect("superadmin_panel:all-client")


def get_default_rate():
    return {"base": 0.0, "additional": 0.0}


@superadmin_required
def assign_courier_and_rates(request, user_id: int):
    """Assign couriers and their rates to a specific user."""
    user = get_object_or_404(User, id=user_id, role=User.USER)
    couriers = Courier.objects.all()
    rates = {}

    if request.method == "POST":
        count = 0
        data = request.POST
        print(data)

        for key, value in data.items():
            if key == "csrfmiddlewaretoken":
                continue

            parts = key.split("_")
            if not key.startswith("table-") or len(parts) < 4:
                continue

            table_prefix = parts[0]  # e.g., table-1
            courier = data.get(f"{table_prefix}_courier", "").strip()
            mode = data.get(f"{table_prefix}_mode", "").strip()
            weight = data.get(f"{table_prefix}_base_weight", "").strip()  # use str
            additional_weight = data.get(
                f"{table_prefix}_additional_weight", ""
            ).strip()  # use str
            cod_charges = data.get(f"{table_prefix}_cod_charges", "").strip()
            cod_percentage = data.get(f"{table_prefix}_cod_percentage", "").strip()
            last_part = parts[-1]  # e.g., fwd1 or rto2
            flow_raw, kind_suffix = last_part[:-1], last_part[-1]

            zone = key.replace(f"{table_prefix}_", "").replace(
                f"_{flow_raw}{kind_suffix}", ""
            )

            # Determine flow and kind
            flow = "forward" if "fwd" in flow_raw else "rto"
            kind = "base" if kind_suffix == "1" else "additional"

            try:
                rate = float(value)

                # Set nested rate, here kind mybe "base" or "additional"
                rates.setdefault(courier, {}).setdefault(mode, {}).setdefault(
                    weight, {}
                ).setdefault(additional_weight, {}).setdefault(zone, {}).setdefault(
                    flow, {}
                )[
                    kind
                ] = rate
                # Set cod charges and percentage manually
                rates.setdefault(courier, {}).setdefault(mode, {}).setdefault(
                    weight, {}
                ).setdefault(additional_weight, {}).setdefault(zone, {}).setdefault(
                    flow, {}
                )[
                    "cod_charges"
                ] = cod_charges
                rates.setdefault(courier, {}).setdefault(mode, {}).setdefault(
                    weight, {}
                ).setdefault(additional_weight, {}).setdefault(zone, {}).setdefault(
                    flow, {}
                )[
                    "cod_percentage"
                ] = cod_percentage
            except ValueError:
                messages.error(request, f"Invalid rate value for {key} - {value}.")

        print(rates)
        """output
        """
        for key, value in rates.items():
            if not key.isdigit():
                messages.warning(request, f"Courier {key} not found.")
                continue
            courier = Courier.objects.filter(id=key).first()
            if not courier:
                messages.error(request, f"Courier {key} not found.")
                continue

            rate_card, created = RateCard.objects.get_or_create(
                courier=courier, user=user
            )
            if mode not in rate_card.courier.available_modes:
                messages.info(
                    request,
                    f"Mode {mode} not found in rate card for {courier.name}. available modes are: {', '.join(rate_card.courier.available_modes)}.",
                )

            for mode, mode_data in value.items():
                for weight, weight_data in mode_data.items():
                    for addl_weight, addl_weight_data in weight_data.items():
                        for zone, zone_data in addl_weight_data.items():
                            for flow, flow_data in zone_data.items():
                                for kind, price in flow_data.items():
                                    try:
                                        rate_card.set_rate(
                                            mode=mode,
                                            weight=weight,
                                            additional_weight=addl_weight,
                                            zone=zone,
                                            flow=flow,
                                            kind=kind,
                                            value=price,
                                        )
                                    except Exception as e:
                                        messages.error(
                                            request,
                                            f"Error setting rate: {e}\t{traceback.format_exc()}",
                                        )

                    count += 1

            rate_card.save()

        messages.success(
            request, f"{count} courier assignments and rates saved successfully."
        )
    couriers = Courier.objects.values("id", "name", "available_modes")
    return render(
        request,
        "superadmin_panel/assign_courier_and_rates.dj",
        {"user": user, "couriers": list(couriers)},
    )


@superadmin_required
def view_rate_cards(request, user_id: int):
    user = get_object_or_404(User, id=user_id)
    return render(request, "superadmin_panel/view_rate_cards.dj", {"user": user})


@superadmin_required
def edit_rate_card(request, rate_card_id: int):
    rate_card = RateCard.objects.filter(user__role=User.USER, id=rate_card_id).first()
    if not rate_card:
        messages.error(request, "Rate card not found.")
        return redirect("superadmin_panel:view-rate-cards")

    if request.method == "POST":
        data = request.POST
        # TODO: complete

    return render(
        request, "superadmin_panel/edit_rate_card.dj", {"rate_card": rate_card}
    )


@superadmin_required
def delete_rate_card(request, rate_card_id: int = None):
    """
    - POST:
        * selected_rate_cards values like:
          - "123_all"
          - "123_surface_0.5_0.5"
        * Deletes full RateCard or removes specific mode/weight/addl_weight
        * Cleans up empty parents
        * Deletes RateCard if data becomes empty
    - GET:
        * Deletes full RateCard via URL param
    """

    if request.method == "POST":
        selected = request.POST.getlist("selected_rate_cards")
        user_id = request.POST.get("user_id")

        if not selected:
            messages.warning(request, "No items selected for deletion.")
            return redirect("superadmin_panel:view-rate-cards", user_id=user_id)

        total_records_deleted = 0
        total_modes_removed = 0

        for sel in selected:
            try:
                parts = sel.split("_")

                rc_id = int(parts[0])
                mode = parts[1]

                rc = RateCard.objects.filter(id=rc_id, user__role=User.USER).first()

                if not rc:
                    continue

                # -----------------------
                # DELETE FULL RATE CARD
                # -----------------------
                if mode == "all":
                    rc.delete()
                    total_records_deleted += 1
                    continue

                # -----------------------
                # DELETE PARTIAL (JSON)
                # -----------------------
                if len(parts) != 4:
                    continue

                _, mode, weight, addl_weight = parts
                data = rc.data or {}

                if (
                    mode in data
                    and weight in data[mode]
                    and addl_weight in data[mode][weight]
                ):
                    # Remove leaf
                    data[mode][weight].pop(addl_weight)

                    # Cleanup empty weight
                    if not data[mode][weight]:
                        data[mode].pop(weight)

                    # Cleanup empty mode
                    if not data[mode]:
                        data.pop(mode)

                    # If everything gone → delete rate card
                    if not data:
                        rc.delete()
                        total_records_deleted += 1
                    else:
                        rc.data = data
                        rc.save(update_fields=["data"])
                        total_modes_removed += 1

            except Exception:
                # Silently ignore malformed input
                continue

        msg_parts = []
        if total_records_deleted:
            msg_parts.append(f"{total_records_deleted} rate card(s) deleted")
        if total_modes_removed:
            msg_parts.append(f"{total_modes_removed} mode(s) removed")

        if msg_parts:
            messages.success(request, " and ".join(msg_parts) + " successfully.")
        else:
            messages.info(request, "No changes were made.")

        return redirect("superadmin_panel:view-rate-cards", user_id=user_id)

    # -----------------------
    # GET → SINGLE DELETE
    # -----------------------
    if rate_card_id is None:
        messages.error(request, "No rate card specified.")
        return redirect("superadmin_panel:dashboard")

    rc = get_object_or_404(RateCard, id=rate_card_id, user__role=User.USER)

    user_id = rc.user.id

    try:
        rc.delete()
        messages.success(request, "Rate card deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting rate card: {e}")

    return redirect("superadmin_panel:view-rate-cards", user_id=user_id)


@superadmin_required
def rate_card(request):
    users = User.objects.filter(role=User.USER).values(
        "id", "full_name", "email", "contact_no"
    )
    return render(request, "superadmin_panel/rate_card.dj", {"users": list(users)})


@superadmin_required
def assign_commission(request):
    if request.method == "GET":
        data = request.GET
        admin_id = data.get("admin_id")
        commission = data.get("commission")
        if admin_id and commission:
            try:
                admin = User.objects.get(id=admin_id, role=User.ADMIN)
                admin.commission = float(commission)
                admin.save()
                messages.success(request, "Commission assigned successfully.")
            except User.DoesNotExist:
                messages.error(request, "Admin not found.")
            except ValueError:
                messages.error(request, "Invalid commission value.")
        else:
            messages.error(request, "admin_id and commission are required.")
    return redirect("superadmin_panel:list-admin")


@superadmin_required
def manage_pincode(request):
    blocked = BlockedPincode.objects.all()
    return render(
        request, "superadmin_panel/manage_pincode.dj", {"blocked_pincodes": blocked}
    )


@superadmin_required
def block_pincodes(request):
    if request.method == "POST":
        data = request.POST
        pincodes = data.getlist("pincodes[]", [])
        reason = data.get("reason", "")
        if not pincodes:
            messages.error(request, "Pincodes required.")
            return redirect("superadmin_panel:manage_pincode")

        count = 0

        for code in pincodes:
            if len(code) == 6 and code.isdigit():
                BlockedPincode.block_pincode(
                    pincode=code, reason=reason, blocked_by=request.user
                )
                count += 1

        messages.success(request, f"{count} pincodes blocked successfully.")

    return redirect("superadmin_panel:manage_pincode")


@superadmin_required
def unblock_pincodes(request):
    if request.method == "POST":
        pincodes = request.POST.getlist("remove_pincodes")
        BlockedPincode.unblock_pincodes(pincodes=pincodes)
        messages.success(request, f"{len(pincodes)} pincodes unblocked successfully.")

    return redirect("superadmin_panel:manage_pincode")


@superadmin_required
def set_min_balance(request):
    if request.method == "POST":
        data = request.POST

        min_balance = data.get("min_balance", "").strip()

        try:
            min_balance = int(min_balance)
        except ValueError:
            messages.warning(request, "Minimum balance must be an integer.")
            return redirect("superadmin_panel:set_min_balance")

        if min_balance >= 0:
            messages.warning(request, "Minimum balance must be a negative integer.")
            return redirect("superadmin_panel:set_min_balance")

        user_id = data.get("user_id")
        try:
            user = User.objects.get(id=user_id, role=User.USER)
            user.min_balance = min_balance
            user.save()
        except User.DoesNotExist:
            messages.error(request, "User not found.")
            return redirect("superadmin_panel:set_min_balance")

        Activity.create_from_request(
            request=request,
            activity_type="min_balance_update",
            activity_description=f"Minimum balance set to {min_balance}",
        )
        messages.success(request, "Minimum balance has been set successfully.")

    return render(request, "superadmin_panel/set_min_balance.dj")


@superadmin_required
def get_users(request):
    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    data = request.GET

    role = data.get("role", "user").strip().lower()
    search_query = data.get("search", "").strip()

    # Validate role
    if role not in User.AVAILABLE_ROLES:
        return JsonResponse({"error": "Invalid role"}, status=400)

    # Base queryset for active users with role
    base_queryset = User.objects.filter(role=role, is_active=True).values(
        "id", "full_name", "email", "contact_no"
    )

    search_users = []
    search_user_ids = []

    if search_query:
        search_qs = base_queryset.filter(
            Q(email__icontains=search_query)
            | Q(contact_no__icontains=search_query)
            | Q(full_name__icontains=search_query)
        )
        search_users = list(search_qs)
        search_user_ids = [user["id"] for user in search_users]

    # Exclude users already in search_users
    users = list(base_queryset.exclude(id__in=search_user_ids))

    return JsonResponse(
        {
            "users": users,
            "search_users": search_users,
        },
        status=200,
    )


@superadmin_required
def send_notification(request):
    User = get_user_model()
    BATCH_SIZE = 1000

    # ------------------------
    # SEND NOTIFICATION
    # ------------------------
    if request.method == "POST":
        message_text = request.POST.get("message", "").strip()

        if not message_text:
            messages.error(request, "Please enter a notification message.")
            return redirect("superadmin_panel:send_notification")

        user_ids = list(
            User.objects.filter(role=User.USER).values_list("id", flat=True)
        )

        if not user_ids:
            messages.warning(request, "No users found.")
            return redirect("superadmin_panel:send_notification")

        notifications_batch = []
        created_count = 0

        for uid in user_ids:
            notifications_batch.append(
                Notification(user_id=uid, msg=message_text, category="info")
            )

            if len(notifications_batch) >= BATCH_SIZE:
                Notification.objects.bulk_create(notifications_batch)
                created_count += len(notifications_batch)
                notifications_batch.clear()

        if notifications_batch:
            Notification.objects.bulk_create(notifications_batch)
            created_count += len(notifications_batch)

        messages.success(request, f"Notification sent to {created_count} users.")
        return redirect("superadmin_panel:send_notification")

    # ------------------------
    # PAGINATION
    # ------------------------
    per_page = request.GET.get("per_page", 20)

    try:
        per_page = int(per_page)
    except ValueError:
        per_page = 20

    notifications_qs = Notification.objects.select_related("user").order_by(
        "-created_at"
    )

    paginator = Paginator(notifications_qs, per_page)
    page_number = request.GET.get("page")
    notifications = paginator.get_page(page_number)

    return render(
        request,
        "superadmin_panel/send_notification.dj",
        {
            "notifications": notifications,
            "per_page": per_page,
        },
    )


@superadmin_required
def user_details(request, user_id):
    user = User.objects.filter(id=user_id).first()
    if not user:
        messages.error(request, "User not found.")
        return redirect("superadmin_panel:all-client")

    return render(request, "superadmin_panel/user_details.dj", {"user": user})


@superadmin_required
def assign_admin(request):
    # 1. Detect if we're in "single‐user" mode
    user_ids_param = request.GET.get("user_ids")
    is_single = bool(user_ids_param)

    # 2. Load admins always
    admins = User.objects.filter(role=User.ADMIN)

    # 3. Load users: either the one user, or all users
    if is_single:
        user = get_object_or_404(User, id=user_ids_param, role=User.USER)
        users = [user]
    else:
        users = User.objects.filter(role=User.USER)

    # 4. Handle form submission
    if request.method == "POST":
        selected_user_ids = request.POST.getlist("user_ids")
        selected_admin_id = request.POST.get("admin_id")

        if not selected_admin_id or not selected_user_ids:
            messages.error(request, "Please select both user(s) and an admin.")
            return redirect(request.get_full_path())

        try:
            admin = User.objects.get(id=selected_admin_id, role=User.ADMIN)
            qs = User.objects.filter(id__in=selected_user_ids, role=User.USER)
            for u in qs:
                u.assigned_admin = admin
                u.save()
            messages.success(
                request, f"Assigned {admin.full_name} to {qs.count()} user(s)."
            )
            return redirect("superadmin_panel:assign-admin")
        except Exception as e:
            messages.error(request, f"Error: {e}")

    # 5. Render the template
    return render(
        request,
        "superadmin_panel/assign_admin.dj",
        {
            "admins": admins,
            "users": users,
            "is_single": is_single,
        },
    )


@superadmin_required
def manage_wallet(request, user_id):
    user = get_object_or_404(User, id=user_id)
    wallet_balance = user.balance

    if request.method == "POST":
        new_balance = request.POST.get("new_balance")
        if new_balance:
            user.wallet_balance = new_balance
            user.save()
            messages.success(request, "Wallet balance updated successfully.")
            return redirect("superadmin_panel:manage-wallet", user_id=user.id)

    return render(
        request,
        "superadmin_panel/manage_wallet.dj",
        {
            "user": user,
            "wallet_balance": wallet_balance,
            "cn_dn_reasons": Transaction.TRANSACTION_DESCRIPTIONS,
            "recent_transactions": Transaction.objects.filter(user=user)[:5],
        },
    )


@superadmin_required
def add_balance(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        amount = request.POST.get("amount")
        reason = request.POST.get("reason")
        other_reason = request.POST.get("other_reason")

        if reason not in [i[0] for i in Transaction.TRANSACTION_DESCRIPTIONS]:
            reason = "other"

        if reason == "other" and not other_reason:
            messages.error(request, "Other reason is required.")
            return redirect("superadmin_panel:manage-wallet", user_id=user.id)

        if amount:
            try:
                amount = float(amount)
            except ValueError:
                messages.error(request, "Invalid amount.")
                return redirect("superadmin_panel:manage-wallet", user_id=user.id)

            tr = Transaction.create_transaction(
                user=user,
                merchant_txn_id=str(uuid.uuid4()),
                amount_rs=amount,
                transaction_type="credit",
                desc=reason or "Wallet recharge by superadmin",
                other_reason=other_reason if reason == "other" else "",
            )
            tr.credit(status="SUCCESS", forcefully=True)
            user.save()
            messages.success(request, "Balance added successfully.")
            return redirect("superadmin_panel:manage-wallet", user_id=user.id)
        else:
            messages.error(request, "Invalid amount.")

    return redirect("superadmin_panel:manage-wallet", user_id=user.id)


@superadmin_required
def deduct_balance(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        try:
            amount = request.POST.get("amount")
            reason = request.POST.get("reason")
            other_reason = request.POST.get("other_reason")

            if reason not in [i[0] for i in Transaction.TRANSACTION_DESCRIPTIONS]:
                reason = "other"

            if reason == "other" and not other_reason:
                messages.error(request, "Other reason is required.")
                return redirect("superadmin_panel:manage-wallet", user_id=user.id)

            if amount:
                try:
                    amount = float(amount)
                except ValueError:
                    messages.error(request, "Invalid amount.")
                    return redirect("superadmin_panel:manage-wallet", user_id=user.id)

                tr = Transaction.create_transaction(
                    user=user,
                    merchant_txn_id=str(uuid.uuid4()),
                    amount_rs=amount,
                    transaction_type="debit",
                    desc=reason or "",
                    other_reason=other_reason if reason == "other" else "",
                )
                tr.debit(status="SUCCESS", forcefully=True)
                user.save()
                messages.success(request, "Balance deducted successfully.")
                return redirect("superadmin_panel:manage-wallet", user_id=user.id)
            else:
                messages.error(request, "Invalid amount.")
        except Exception as e:
            messages.error(request, f"Error: {e}")

    return redirect("superadmin_panel:manage-wallet", user_id=user.id)


@superadmin_required
def set_debit_limit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        debit_limit = request.POST.get("amount")

        if debit_limit:
            try:
                debit_limit = float(debit_limit)

                user.min_balance = debit_limit
                user.save()

                messages.success(request, "Debit limit set successfully.")
            except ValueError:
                messages.error(request, "Invalid debit limit value.")
                return redirect("superadmin_panel:manage-wallet", user_id=user.id)
        else:
            messages.error(request, "Debit limit cannot be empty.")

    return redirect("superadmin_panel:manage-wallet", user_id=user.id)
