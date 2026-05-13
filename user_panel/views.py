# Standard library imports
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import re
import logging
import zipfile
import importlib
import requests
import csv
from urllib.parse import urlparse
from collections import defaultdict, OrderedDict

# Third-party imports
from typing import Optional
from datetime import datetime, timedelta
from io import BytesIO
from PyPDF2 import PdfMerger
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

# Django imports
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import IntegrityError
from django.db.models import (
    Sum,
    Count,
    QuerySet,
    Q,
    Min,
    F,
    Avg,
    ExpressionWrapper,
    DurationField,
)
from django.db.models.functions import TruncMonth, TruncDay, TruncDate, Lower, Trim
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now, make_aware, localtime


# Local app imports
from account.decorators import user_required
from account.models import Courier, CourierPreferenceSequence, Invoice, Notice
from order_manager.export_orders import generate_bulk_export_response
from order_manager.helper import validate_hub
from order_manager.models import CODRemittance, Hub, Order, OrderItem, Payment, Shipment
from shopify_integration.models import ShopifyStore
from user_panel.validators import filter_orders
from utils.get_courier_handler import get_courier_handler
from utils.pagination import paginate_queryset
from wallet.models import Transaction

# Create your views here.


logger = logging.getLogger("my-logger")


@user_required
def statistics(request):
    """View to return statistics data as JSON for dashboard charts."""
    today = now().date()
    start_of_year = today.replace(month=1, day=1)
    last_7_days = today - timedelta(days=6)

    # 1. Revenue Data - Monthly
    monthly_data = (
        Order.objects.filter(created_at__date__gte=start_of_year)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            total_income=Sum("total_amount"),
            total_cod=Sum("payment__cod_charges"),
            total_shipping=Sum("total_amount"),
        )
        .order_by("month")
    )

    labels = [
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
    ]
    income_data = [0] * 12
    expenses_data = [0] * 12

    for entry in monthly_data:
        month_idx = entry["month"].month - 1
        income = entry["total_income"] or 0
        expenses = (entry["total_cod"] or 0) + (entry["total_shipping"] or 0)
        income_data[month_idx] = income
        expenses_data[month_idx] = expenses

    sales_by_courier = (
        Order.objects.filter(logistic_partner__isnull=False)
        .values("logistic_partner__name")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    courier_labels = [item["logistic_partner__name"] for item in sales_by_courier]
    courier_series = [item["total"] for item in sales_by_courier]

    # 3. Daily Sales - This Week
    daily_data = (
        Order.objects.filter(created_at__date__gte=last_7_days)
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(sales=Sum("total_amount"))
        .order_by("day")
    )

    weekday_labels = ["Sun", "Mon", "Tue", "Wed", "Thur", "Fri", "Sat"]
    daily_sales_data = [0] * 7

    for entry in daily_data:
        weekday = entry["day"].weekday()  # 0=Mon ... 6=Sun
        daily_sales_data[weekday] = float(entry["sales"] or 0)

    # 4. Total Orders Summary
    total_orders = Order.objects.count()
    recent_orders_qs = Order.objects.select_related("user").order_by("-created_at")[:5]

    total_order_series = list(
        Order.objects.order_by("-created_at").values_list("total_amount", flat=True)[
            :10
        ]
    )

    # 5. Summary
    total_income = sum(income_data)
    total_expenses = sum(expenses_data)
    total_profit = total_income - total_expenses

    summary = {
        "income": total_income,
        "expenses": total_expenses,
        "profit": total_profit,
        "income_percent": min(100, int((total_income / 100000) * 100)),
        "expenses_percent": min(100, int((total_expenses / 100000) * 100)),
        "profit_percent": min(100, int((total_profit / 100000) * 100)),
    }

    # 6. Recent Orders
    recent_orders = []
    for order in recent_orders_qs:
        recent_orders.append(
            {
                "image": (
                    order.user.profile_image.url
                    if hasattr(order.user, "profile_image")
                    else "/media/default/user_logo.png"
                ),
                "name": (
                    order.user.name if hasattr(order.user, "name") else str(order.user)
                ),
                "product_name": f"Order #{order.id}",
                "price": str(order.total_amount),
                "status": order.status,
            }
        )

    response = {
        "last_updated": timezone.localtime().strftime("%Y-%m-%d %I:%M%p"),
        "revenue": {
            "total_profit": total_profit,
            "labels": labels,
            "series": [
                {"name": "Income", "data": income_data},
                {"name": "Expenses", "data": expenses_data},
            ],
        },
        "sales_by_category": {
            "labels": courier_labels,
            "series": courier_series,
        },
        "daily_sales": {
            "labels": weekday_labels,
            "series": [
                {"name": "Sales", "data": daily_sales_data},
                {"name": "Last Week", "data": [0] * 7},  # Optional
            ],
        },
        "total_orders": {
            "total": total_orders,
            "series": [{"name": "Sales", "data": total_order_series}],
        },
        "summary": summary,
        "recent_orders": recent_orders,
    }

    return JsonResponse(response)


# ---------------------------------------------------
# Helper: Growth Calculation
# ---------------------------------------------------
def calculate_growth(current: int, previous: int):
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 2)


# ---------------------------------------------------
# Helper: Avg TAT
# ---------------------------------------------------
def avg_tat(order_qs):
    shipments = Shipment.objects.filter(order__in=order_qs, delivered_at__isnull=False)

    tat_list = [
        (s.delivered_at - s.created_at).days
        for s in shipments
        if s.delivered_at and s.created_at
    ]

    return round(sum(tat_list) / len(tat_list), 2) if tat_list else 0


# ---------------------------------------------------
# DASHBOARD VIEW
# ---------------------------------------------------
@user_required
def dashboard(request):
    if request.method != "GET":
        messages.info(request, "Method not allowed")
        return redirect("user_panel:dashboard")

    data = request.GET

    date_from = data.get("date_from")
    date_to = data.get("date_to")
    payment_method = data.get("method")
    courier = data.get("courier")
    show_notice = data.get("show_notice")

    # date times
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)

    # ---------------------------------------------------
    # Base Querysets
    # ---------------------------------------------------
    current_orders = Order.objects.filter(user=request.user).exclude(
        status__in=["cancelled", "ready_to_ship"]
    )
    previous_orders = Order.objects.filter(user=request.user).exclude(
        status__in=["cancelled", "ready_to_ship"]
    )

    # ---------------------------------------------------
    # Date Filter + Previous Period
    # ---------------------------------------------------
    if date_from and date_to:
        try:
            start_date = datetime.strptime(date_from, "%m/%d/%Y")
            end_date = datetime.strptime(date_to, "%m/%d/%Y")

            # Current Period
            current_orders = current_orders.filter(
                created_at__date__range=(start_date, end_date)
            )

            # Previous Period
            days = (end_date - start_date).days + 1

            prev_end = start_date - timedelta(days=1)
            prev_start = prev_end - timedelta(days=days - 1)

            previous_orders = previous_orders.filter(
                created_at__date__range=(prev_start, prev_end)
            )

        except Exception as e:
            logger.exception(e)
    else:
        current_orders = current_orders.filter(
            created_at__date__gte=now().date() - timedelta(days=7)
        )

    # ---------------------------------------------------
    # Payment Filter
    # ---------------------------------------------------
    if payment_method and payment_method != "all":
        current_orders = current_orders.filter(payment__method=payment_method)
        previous_orders = previous_orders.filter(payment__method=payment_method)

    # ---------------------------------------------------
    # Courier Filter
    # ---------------------------------------------------
    if courier and courier != "all":
        current_orders = current_orders.filter(logistic_partner__id=courier)
        previous_orders = previous_orders.filter(logistic_partner__id=courier)

    # ---------------------------------------------------
    # Total Shipments
    # ---------------------------------------------------
    total_current = current_orders.count()
    total_previous = previous_orders.count()

    shipment_growth = calculate_growth(total_current, total_previous)

    # ---------------------------------------------------
    # Delivered + Delivery Rate
    # ---------------------------------------------------
    delivered_current = current_orders.filter(status="delivered").count()
    delivered_previous = previous_orders.filter(status="delivered").count()

    delivery_rate_current = (
        (delivered_current / total_current) * 100 if total_current else 0
    )

    delivery_rate_previous = (
        (delivered_previous / total_current) * 100 if total_current else 0
    )

    delivery_rate_growth = calculate_growth(
        delivery_rate_current, delivery_rate_previous
    )

    # ---------------------------------------------------
    # In Transit
    # ---------------------------------------------------
    in_transit_current = current_orders.filter(status="in_transit").count()
    in_transit_previous = previous_orders.filter(status="in_transit").count()

    in_transit_growth = calculate_growth(in_transit_current, in_transit_previous)

    # ---------------------------------------------------
    # RTO Rate
    # ---------------------------------------------------
    rto_current = current_orders.filter(status__startswith="rto").count()
    rto_previous = previous_orders.filter(status__startswith="rto").count()

    rto_rate_current = (rto_current / total_current) * 100 if total_current else 0

    rto_rate_previous = (rto_previous / total_previous) * 100 if total_previous else 0

    rto_rate_growth = calculate_growth(rto_rate_current, rto_rate_previous)

    # ---------------------------------------------------
    # Average TAT
    # ---------------------------------------------------
    tat_current = avg_tat(current_orders)
    tat_previous = avg_tat(previous_orders)

    tat_growth = calculate_growth(tat_current, tat_previous)
    today_shipment = Order.objects.filter(user=request.user, status="pending_pickup")
    yesterday_shipment = Order.objects.filter(
        user=request.user,
        status="ready_to_ship",
        shipment__booked_at__date=yesterday,
    )
    if date_from and date_to:
        today_shipment = today_shipment.filter(
            created_at__date__range=(start_date, end_date)
        )
        yesterday_shipment = yesterday_shipment.filter(
            created_at__date__range=(start_date, end_date)
        )

    if courier and courier != "all":
        today_shipment = today_shipment.filter(logistic_partner__id=courier)
        yesterday_shipment = yesterday_shipment.filter(logistic_partner__id=courier)

    if courier and courier != "all":
        today_shipment = today_shipment.filter(logistic_partner__id=courier)
        yesterday_shipment = yesterday_shipment.filter(logistic_partner__id=courier)

    today_shipment = today_shipment.count()
    yesterday_shipment = yesterday_shipment.count()
    # ---------------------------------------------------
    # Status Summary
    # ---------------------------------------------------
    status_summary = {
        "placed": {
            "value": today_shipment,
            "growth": calculate_growth(
                today_shipment,
                previous_orders.filter(status="pending_pickup").count(),
            ),
        },
        "ready_to_ship": {
            "value": Order.objects.filter(
                user=request.user, status="ready_to_ship"
            ).count(),
            "growth": calculate_growth(
                current_orders.filter(status="ready_to_ship").count(),
                previous_orders.filter(status="ready_to_ship").count(),
            ),
        },
        "in_transit": {
            "value": current_orders.filter(status="in_transit").count(),
            "growth": calculate_growth(
                current_orders.filter(status="in_transit").count(),
                previous_orders.filter(status="in_transit").count(),
            ),
        },
        "out_for_delivery": {
            "value": current_orders.filter(status="out_for_delivery").count(),
            "growth": calculate_growth(
                current_orders.filter(status="out_for_delivery").count(),
                previous_orders.filter(status="out_for_delivery").count(),
            ),
        },
        "delivered": {
            "value": current_orders.filter(status="delivered").count(),
            "growth": calculate_growth(
                current_orders.filter(status="delivered").count(),
                previous_orders.filter(status="delivered").count(),
            ),
        },
        "failed_delivery": {
            "value": current_orders.filter(status__in=["ndr", "exception"]).count(),
            "growth": calculate_growth(
                current_orders.filter(status__in=["ndr", "exception"]).count(),
                previous_orders.filter(status__in=["ndr", "exception"]).count(),
            ),
        },
        "cancelled": {
            "value": Order.objects.filter(
                user=request.user, status="cancelled"
            ).count(),
            "growth": calculate_growth(
                Order.objects.filter(user=request.user, status="cancelled").count(),
                previous_orders.filter(status="cancelled").count(),
            ),
        },
        "rto": {
            "value": current_orders.filter(status__startswith="rto").count(),
            "growth": calculate_growth(
                current_orders.filter(status__startswith="rto").count(),
                previous_orders.filter(status__startswith="rto").count(),
            ),
        },
        "lost": {
            "value": current_orders.filter(status="lost").count(),
            "growth": calculate_growth(
                current_orders.filter(status="lost").count(),
                previous_orders.filter(status="lost").count(),
            ),
        },
    }

    # ---------------------------------------------------
    # Courier Dropdown Data
    # ---------------------------------------------------
    couriers = Courier.objects.filter(orders__user=request.user).distinct()

    last_5_days = []
    for i in range(4, -1, -1):
        day = today - timedelta(days=i)

        orders_count = (
            Order.objects.filter(user=request.user, shipment__booked_at__date=day)
            .exclude(status__in=["cancelled", "ready_to_ship"])
            .count()
        )

        last_5_days.append(
            {
                "day": day.strftime("%a"),
                "date": day.strftime("%d/%m/%Y"),
                "orders": orders_count,
            }
        )

    # ---------------------------------------------------
    # Top 5 Couriers
    # ---------------------------------------------------
    courier_data = (
        current_orders.values("logistic_partner__name")
        .annotate(total_orders=Count("id"))
        .order_by("-total_orders")[:5]
    )

    total_orders_for_percentage = current_orders.count() or 1

    top_5_couriers = {}

    for c in courier_data:
        name = c.get("logistic_partner__name")
        if not name:
            continue

        orders = c["total_orders"]

        top_5_couriers[name] = {
            "orders": orders,
            "percentage": round((orders / total_orders_for_percentage) * 100, 2),
        }

    # ---------------------------------------------------
    # COD vs Prepaid
    # ---------------------------------------------------
    cod_count = (
        current_orders.filter(payment__method="cod")
        .exclude(status__in=["cancelled", "ready_to_ship"])
        .count()
    )
    prepaid_count = current_orders.exclude(payment__method="cod").count()

    cod_vs_prepaid = {"cod": cod_count, "prepaid": prepaid_count}

    # ---------------------------------------------------
    # Pickup Completion
    # ---------------------------------------------------
    completed_pickups = Order.objects.filter(
        user=request.user,
        shipment__booked_at__date=now().date(),
        status="in_transit",
    ).count()

    total_pickups = Order.objects.filter(
        user=request.user,
        shipment__booked_at__date=now().date(),
    ).count()

    pickup_completion = {"completed": completed_pickups, "total_pickups": total_pickups}

    # ---------------------------------------------------
    # Total Shipments
    # ---------------------------------------------------
    total_shipments = Order.objects.filter(
        user=request.user,
    )

    try:
        if start_date and end_date:
            total_shipments = total_shipments.filter(
                created_at__date__range=(start_date, end_date)
            )
        else:
            total_shipments = total_shipments.filter(
                created_at__date__gte=now().date() - timedelta(days=7)
            )
    except:
        total_shipments = total_shipments.filter(
            created_at__date__gte=now().date() - timedelta(days=7)
        )

    # ---------------------------------------------------
    # Context
    # ---------------------------------------------------
    ctx = {
        "couriers": couriers,
        "total_shipments": total_shipments.count(),
        "shipment_growth": shipment_growth,
        "delivery_rate": round(delivery_rate_current, 2),
        "delivery_rate_growth": delivery_rate_growth,
        "in_transit": in_transit_current,
        "in_transit_growth": in_transit_growth,
        "rto_rate": round(rto_rate_current, 2),
        "rto_rate_growth": rto_rate_growth,
        "avg_tat": tat_current if tat_current > 0 else 0,
        "tat_growth": tat_growth if tat_growth > 0 else 0,
        "status_summary": status_summary,
        "total_daily_orders": last_5_days,
        "top_5_couriers": top_5_couriers,
        "cod_vs_prepaid": cod_vs_prepaid,
        "pickup_completion": pickup_completion,
    }
    if show_notice:
        ctx["notices"] = Notice.get_active_notice()

    return render(request, "user_panel/dashboard_new.dj", ctx)


def get_revenue_data(user, orders_queryset: QuerySet[Order], months=12):
    """
    Get revenue data for the last N months, split by prepaid and COD.
    """
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30 * months)

    # Get orders by month and payment type
    orders = (
        orders_queryset.filter(user=user, order_date__range=[start_date, end_date])
        .values("order_date__month", "order_date__year", "payment__method")
        .annotate(total_amount=Sum("total_amount"))
        .order_by("order_date__year", "order_date__month")
    )

    # Initialize data structure
    months_data = {}
    for i in range(months):
        month = (end_date - timedelta(days=30 * i)).strftime("%b")
        months_data[month] = {"prepaid": 0, "cod": 0}

    # Populate data
    for order in orders:
        month = order["order_date__month"]
        year = order["order_date__year"]
        month_key = timezone.datetime(year, month, 1).strftime("%b")
        payment_method = order["payment__method"] or "prepaid"

        if payment_method == "prepaid":
            months_data[month_key]["prepaid"] += float(order["total_amount"] or 0)
        else:
            months_data[month_key]["cod"] += float(order["total_amount"] or 0)

    # Convert to chart format
    months_list = list(months_data.keys())[::-1]  # Reverse to show oldest first
    prepaid_data = [months_data[month]["prepaid"] for month in months_list]
    cod_data = [months_data[month]["cod"] for month in months_list]

    return {
        "series": [
            {"name": "Prepaid Packet Delivered Amount", "data": prepaid_data},
            {"name": "COD Packet Delivered Amount", "data": cod_data},
        ],
        "categories": months_list,
    }


def get_category_data(user, orders_queryset: QuerySet[Order]):
    """Get courier distribution data."""
    orders = (
        orders_queryset.filter(user=user)
        .values("logistic_partner__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    courier_data = {}
    total = 0

    for order in orders:
        courier_name = order["logistic_partner__name"] or "Unknown"
        courier_data[courier_name] = order["count"]
        total += order["count"]

    # Default couriers if no data
    if not courier_data:
        courier_data = {"Xbees": 50, "Delhivery": 30, "Bluedart": 20}
        total = 100

    # Convert to percentages for chart
    labels = list(courier_data.keys())
    series = [courier_data[label] for label in labels]

    return {"series": series, "labels": labels, "total": total}


def get_daily_sales_data(user, orders_queryset, days=7):
    """Get daily sales by courier for the last N days."""
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)

    # Initialize dictionary for last N days
    daily_data = {}
    date_list = [(start_date + timedelta(days=i)) for i in range(days)]
    for d in date_list:
        day_name = d.strftime("%a")
        daily_data[day_name] = {}

    # Query orders within date range
    orders = (
        orders_queryset.filter(
            user=user,
            order_date__date__gte=start_date,
            order_date__date__lte=end_date,
        )
        .values("order_date__date", "logistic_partner__name")
        .annotate(count=Count("id"))
    )

    # Fill data dynamically (no hard-coded couriers)
    for order in orders:
        date = order["order_date__date"]
        courier = order["logistic_partner__name"] or "Unknown"
        day_name = date.strftime("%a")

        if day_name not in daily_data:
            daily_data[day_name] = {}
        daily_data[day_name][courier] = (
            daily_data[day_name].get(courier, 0) + order["count"]
        )

    # Prepare list of couriers (from data)
    couriers = set()
    for day_values in daily_data.values():
        couriers.update(day_values.keys())
    couriers = sorted(couriers)

    # Convert to chart format
    days_list = [d.strftime("%a") for d in date_list]
    series = []
    for courier in couriers:
        courier_data = [daily_data[day].get(courier, 0) for day in days_list]
        series.append({"name": courier, "data": courier_data})

    return {"series": series, "categories": days_list}


def get_summary_data(user):
    """Get summary data for prepaid and COD orders"""
    prepaid_total = (
        Payment.objects.filter(
            order__user=user, method="prepaid", status="completed"
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    cod_total = (
        Payment.objects.filter(
            order__user=user, method="cod", status="completed"
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    total_revenue = prepaid_total + cod_total
    prepaid_percentage = (
        int((prepaid_total / total_revenue * 100)) if total_revenue > 0 else 0
    )
    cod_percentage = int((cod_total / total_revenue * 100)) if total_revenue > 0 else 0

    return {
        "prepaid": {"amount": float(prepaid_total), "progress": prepaid_percentage},
        "cod": {"amount": float(cod_total), "progress": cod_percentage},
    }


def get_total_orders_data(user, hours=24):
    """Get total orders count and trend data"""
    total_orders = Order.objects.filter(user=user).count()

    # Generate trend data (simplified - you can make this real)
    trend_data = [total_orders - i * 2 for i in range(hours)]
    trend_data = [max(0, x) for x in trend_data]  # Ensure no negative values

    return {
        "count": total_orders,
        "trend": trend_data[-24:],  # Last 24 data points
    }


def get_recent_activities(user, limit=10):
    """Get recent activities for the user"""
    activities = []

    # Recent orders
    recent_orders = Order.objects.filter(user=user).order_by("-order_date")[:5]
    for order in recent_orders:
        activities.append(
            {
                "type": "primary",
                "content": f"New order #{order.order_number} created",
                "time": get_time_ago(order.order_date),
                "badge": "Order",
            }
        )

    # Recent payments
    recent_payments = Payment.objects.filter(
        order__user=user, status="completed"
    ).order_by("-processed_at")[:5]
    for payment in recent_payments:
        activities.append(
            {
                "type": "success",
                "content": f"Payment received for order #{payment.order.order_number}",
                "time": get_time_ago(payment.processed_at),
                "badge": "Payment",
            }
        )

    # Sort by time and limit
    activities.sort(key=lambda x: x["time"], reverse=True)
    return activities[:limit]


def get_recent_transactions(user, limit=5):
    """Get recent wallet transactions"""
    transactions = Transaction.objects.filter(user=user, status="SUCCESS").order_by(
        "-created_at"
    )[:limit]

    transaction_list = []
    for txn in transactions:
        transaction_list.append(
            {
                "type": "CR" if txn.transaction_type == "credit" else "DB",
                "title": txn.get_desc_display(),
                "time": txn.created_at.strftime("%d %b %I:%M%p"),
                "amount": float(txn.amount),
                "is_credit": txn.transaction_type == "credit",
            }
        )

    return transaction_list


def get_wallet_balance(user):
    """Get user wallet balance"""
    return float(user.balance)


def get_recent_orders(user, orders_queryset: QuerySet[Order], limit=5):
    """Get recent orders for table"""
    orders = (
        orders_queryset.filter(user=user)
        .select_related("shipping_address")
        .order_by("-order_date")[:limit]
    )

    order_list = []
    for order in orders:
        order_list.append(
            {
                "customer_name": (
                    order.shipping_address.name if order.shipping_address else "N/A"
                ),
                "product": "Multiple Products",  # You can enhance this
                "price": float(order.total_amount),
                "status": order.get_status_display(),
                "status_class": get_status_class(order.status),
            }
        )

    return order_list


def get_top_selling_products(user, limit=3):
    """Get top selling products"""
    top_products = (
        OrderItem.objects.filter(order__user=user)
        .values("product__name", "product__price")
        .annotate(total_sold=Sum("quantity"), total_revenue=Sum("total_price"))
        .order_by("-total_sold")[:limit]
    )

    product_list = []
    sources = ["Direct", "Google", "Ads"]

    for i, product in enumerate(top_products):
        product_list.append(
            {
                "name": product["product__name"],
                "category": "Digital",  # You can enhance this
                "price": float(product["product__price"]),
                "discount": float(product["product__price"] * 0.3),  # Sample discount
                "sold": product["total_sold"],
                "source": sources[i] if i < len(sources) else "Direct",
                "source_class": get_source_class(
                    sources[i] if i < len(sources) else "Direct"
                ),
            }
        )

    return product_list


# Helper functions
def get_time_ago(dt):
    """Convert datetime to human readable time ago"""
    now = timezone.now()
    diff = now - dt

    if diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hours ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} min ago"
    else:
        return "Just now"


def get_status_class(status):
    """Get CSS class for status"""
    status_map = {
        "delivered": "success",
        "processing": "warning",
        "cancelled": "danger",
        "shipped": "warning",
    }
    return status_map.get(status, "secondary")


def get_source_class(source):
    """Get CSS class for source"""
    source_map = {"Direct": "danger", "Google": "success", "Ads": "warning"}
    return source_map.get(source, "secondary")


@user_required
def add_order(request):
    def _to_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    context = {
        "bulk_summary": {
            "total": _to_int(request.GET.get("bulk_total")),
            "successful": _to_int(request.GET.get("bulk_success")),
            "failed": _to_int(request.GET.get("bulk_failed")),
            "completed": request.GET.get("bulk_completed") == "1",
            "download_key": request.GET.get("bulk_download_key", ""),
        },
        "active_tab": request.GET.get("active_tab", "create"),
    }
    return render(request, "user_panel/order/b2c_order.html", context)


@user_required
def add_order_new(request):
    return render(request, "user_panel/order/add_order_new.dj")


@user_required
def add_reverse_order(request):
    return render(request, "user_panel/order/add_reverse_order.dj")


@user_required
def failed_order(request):
    return render(request, "user_panel/order/failed_order.dj")


@user_required
def order_details(request, id: int):
    order = get_object_or_404(Order, id=id, user=request.user)

    return render(request, "user_panel/order/order_details.dj", {"order": order})


@user_required
def cancelled_order(request):
    """View for cancelled orders with filtering and export."""
    if request.method != "GET":
        messages.info(request, "Method not allowed")
        return redirect("user_panel:dashboard")

    status = "cancelled"

    data = request.GET
    is_export = data.get("exportOrders", "false").lower() == "true"

    order, page_obj, page_size = filter_orders(
        request, data, status, Order.objects.filter(status=status, user=request.user)
    )

    if is_export:
        return generate_bulk_export_response(order)

    context = {
        "page_obj": page_obj,
        "page_size": page_size,
        "status": status,
        "status_display": Order.ORDER_MAPPING[status],
        "current_params": data.urlencode(),
        "count": {
            "cancelled": Order.objects.filter(
                status="cancelled", user=request.user
            ).count(),
        },
        "couriers": Courier.objects.values("id", "name"),
    }

    return render(request, "user_panel/order/cancelled_order.dj", context)


@user_required
def shipment(request, status: str):
    """View for shipments with filtering and export."""
    ALL_ORDER_STATUS: str = "all_orders"

    if request.method != "GET":
        messages.info(request, "Method not allowed")
        return redirect("user_panel:dashboard")

    data = request.GET

    order, page_obj, page_size, err = filter_orders(request, data, status)
    if err:
        return redirect("user_panel:dashboard")

    if data.get("exportOrders", "false").lower() == "true":
        try:
            return generate_bulk_export_response(order)
        except Exception as e:
            messages.info(request, f"Error while exporting order: {e}")
            return redirect("user_panel:dashboard")

    context = {
        "page_obj": page_obj,
        "page_size": page_size,
        "status": status,
        "status_display": (
            "All Orders" if status == ALL_ORDER_STATUS else Order.ORDER_MAPPING[status]
        ),
        "current_params": data.urlencode(),
        "count": {},
        "couriers": Courier.objects.values("id", "name"),
        "label_page_size": request.user.get_label_setting().label_page_size,
        "new_label": request.user.get_label_setting().new_label,
    }

    count_status = [
        ALL_ORDER_STATUS,
        "ready_to_ship",
        "processing",
        "pending_pickup",
        "in_transit",
        "out_for_delivery",
        "delivered",
        "rto",
        "cancelled",
    ]
    for s in count_status:
        if s == status:
            context["count"][s] = order.count()
        elif s == ALL_ORDER_STATUS:
            context["count"][s] = Order.objects.filter(user=request.user).count()
        else:
            context["count"][s] = Order.objects.filter(
                status__startswith=s, user=request.user
            ).count()

    return render(request, f"user_panel/shipment/{status}.dj", context)


@user_required
def add_hub(request):
    """View to add a new hub for the user."""
    if request.method == "POST":
        data = request.POST
        # validate
        name = data.get("name", "")
        address_line1 = data.get("address_line1", "")
        address_line2 = data.get("address_line2", "")
        city = data.get("city", "")
        state = data.get("state", "")
        country = data.get("country", "")
        pin_code = data.get("pin_code", "")
        contact_person = data.get("contact_person", "")
        phone = data.get("phone", "")
        alt_phone = data.get("alt_phone", "")
        email = data.get("email", "")
        gstin = data.get("gstin", "")

        if Hub.objects.filter(name=name).exists():
            messages.warning(request, "Hub name already taken")
            return redirect("user_panel:add-hub")

        if name and len(name) > 20:
            messages.error(
                request, "Hub name should be a maximum of 20 characters long"
            )
            return redirect("user_panel:add-hub")

        validation_result = validate_hub(
            name,
            address_line1,
            address_line2,
            city,
            state,
            country,
            pin_code,
            contact_person,
            phone,
            alt_phone,
            email,
            gstin,
        )

        if validation_result is not None:
            messages.error(request, validation_result)
            return redirect(
                "user_panel:add-hub"
            )  # or render same page with data prefilled

        try:
            hub = Hub.objects.create(
                name=name,
                address_line1=address_line1,
                address_line2=address_line2,
                city=city,
                state=state,
                country=country,
                pin_code=pin_code,
                contact_person=contact_person,
                phone=phone,
                alt_phone=alt_phone,
                email=email,
                gstin=gstin,
                user=request.user,
            )
        except IntegrityError:
            messages.warning(
                request,
                "Hub name already exists. Please try again with a different name.",
            )
        return redirect("user_panel:all-hub")
    elif request.method == "GET":
        hub = Hub.objects.filter(
            user=request.user, is_active=True, id=request.GET.get("id")
        ).first()

    ctx = {"hub": hub}
    return render(request, "user_panel/hub/add_hub.dj", ctx)


@user_required
def all_hub(request):
    hubs = Hub.objects.filter(user=request.user)
    ctx = {"hubs": hubs}
    return render(request, "user_panel/hub/all_hub.dj", ctx)


@user_required
def edit_hub(request):
    """View to edit an existing hub."""
    return JsonResponse({"success": False, "message": "Feature Disabled"})
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("user_panel:all-hub")

    data = request.POST
    hub_id = data.get("hub_id")

    hub = Hub.objects.filter(user=request.user, id=hub_id).first()
    if not hub:
        messages.error(request, "Invalid Hub.")
        return redirect("user_panel:all-hub")

    # Extract data
    name = data.get("name", "")
    address_line1 = data.get("address_line1", "")
    address_line2 = data.get("address_line2", "")
    city = data.get("city", "")
    state = data.get("state", "")
    country = data.get("country", "")
    pin_code = data.get("pin_code", "")
    contact_person = data.get("contact_person", "")
    phone = data.get("phone", "")
    alt_phone = data.get("alt_phone", "")
    email = data.get("email", "")
    gstin = data.get("gstin", "")

    # Validate data
    validation_result = validate_hub(
        name,
        address_line1,
        address_line2,
        city,
        state,
        country,
        pin_code,
        contact_person,
        phone,
        alt_phone,
        email,
        gstin,
    )

    if validation_result is not None:
        messages.error(request, validation_result)
        return redirect("user_panel:all-hub")

    # Save changes
    hub.name = name
    hub.address_line1 = address_line1
    hub.address_line2 = address_line2
    hub.city = city
    hub.state = state
    hub.country = country
    hub.pin_code = pin_code
    hub.contact_person = contact_person
    hub.phone = phone
    hub.alt_phone = alt_phone
    hub.email = email
    hub.gstin = gstin
    hub.save()

    messages.success(request, "Hub updated successfully.")
    return redirect("user_panel:all-hub")


@user_required
def make_primary_hub(request):
    """View to set a hub as primary."""
    if request.method != "GET":
        messages.error(request, "invalid request method")
        return redirect("user_panel:all-hub")

    hub_id = request.GET.get("id")
    hub = Hub.objects.filter(
        user=request.user, id=hub_id, is_active=True, is_primary=False
    ).first()
    if hub is None:
        messages.error(request, "Invalid Hub Or Hub is already primary.")
        return redirect("user_panel:all-hub")

    for h in Hub.objects.filter(user=request.user):
        h.is_primary = False
        h.save()

    hub.is_primary = True
    hub.save()

    messages.success(request, "Hub updated successfully.")
    return redirect("user_panel:all-hub")


@user_required
def deactivate_hub(request):
    """View to deactivate a hub."""
    if request.method != "GET":
        messages.error(request, "invalid request method")
        return redirect("user_panel:all-hub")

    hub_id = request.GET.get("id")
    hub = Hub.objects.filter(user=request.user, id=hub_id, is_active=True).first()
    if hub is None:
        messages.error(request, "Invalid Hub.")
        return redirect("user_panel:all-hub")

    hub.is_active = False
    hub.save()

    messages.success(request, "Hub updated successfully.")
    return redirect("user_panel:all-hub")


@user_required
def analytics(request):
    """View to return analytics data as JSON for dashboard."""
    if request.method == "GET" and "getData" in request.GET:
        # Total orders, in_transit, delivered, rto (current and last month)
        user = request.user
        orders_queryset = Order.objects.filter(
            user=user, logistic_partner__isnull=False
        )
        today = timezone.localdate()
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)

        def get_count(status=None, start=None, end=None):
            qs = orders_queryset
            if status:
                qs = qs.filter(status=status)
            if start:
                qs = qs.filter(created_at__date__gte=start)
            if end:
                qs = qs.filter(created_at__date__lte=end)
            return qs.count()

        statistics = {
            "total_orders": {
                "value": get_count(start=first_day_this_month, end=today),
                "last_month": get_count(
                    start=first_day_last_month, end=last_day_last_month
                ),
            },
            "in_transit": {
                "value": get_count("in_transit", first_day_this_month, today),
                "last_month": get_count(
                    "in_transit", first_day_last_month, last_day_last_month
                ),
            },
            "delivered": {
                "value": get_count("delivered", first_day_this_month, today),
                "last_month": get_count(
                    "delivered", first_day_last_month, last_day_last_month
                ),
            },
            "rto": {
                "value": get_count("rto", first_day_this_month, today),
                "last_month": get_count(
                    "rto", first_day_last_month, last_day_last_month
                ),
            },
        }

        # Current month data
        current_month_data = {
            "total_orders": get_count(start=first_day_this_month, end=today),
            "pickup_pending": get_count("pending_pickup", first_day_this_month, today),
            "in_transit": get_count("in_transit", first_day_this_month, today),
            "ofd": get_count("out_for_delivery", first_day_this_month, today),
            "delivered": get_count("delivered", first_day_this_month, today),
            "rto": get_count("rto", first_day_this_month, today),
        }

        # Last month data
        last_month_data = {
            "total_orders": get_count(
                start=first_day_last_month, end=last_day_last_month
            ),
            "delivered": get_count(
                "delivered", first_day_last_month, last_day_last_month
            ),
            "rto": get_count("rto", first_day_last_month, last_day_last_month),
        }

        # State wise load (top 6 states by order count this month)
        state_wise = orders_queryset.annotate(count=Count("id")).order_by("-count")
        state_wise_load = {
            "current": {
                entry["shipping_address__state"] or "Unknown": entry.get("count", 0)
                for entry in state_wise.values("shipping_address__state")
            },
            "prev": {
                entry["shipping_address__state"] or "Unknown": entry.get("count", 0)
                for entry in state_wise.filter(
                    created_at__date__gte=first_day_last_month,
                    created_at__date__lt=first_day_this_month,
                ).values("shipping_address__state")
            },
        }

        # Courier wise status (for top 2 couriers)
        courier_status = {}
        couriers = (
            orders_queryset.filter(
                created_at__date__gte=first_day_this_month,
                created_at__date__lte=today,
            )
            .values("logistic_partner__name")
            .annotate(total=Count("id"))
            .order_by("-total")[:2]
        )
        for c in couriers:
            name = c["logistic_partner__name"]
            courier_status[name.lower()] = {
                "total": Order.objects.filter(
                    user=user, logistic_partner__name=name
                ).count(),
                "unshipped": Order.objects.filter(
                    user=user, logistic_partner__name=name, status="pending_pickup"
                ).count(),
                "pending": Order.objects.filter(
                    user=user, logistic_partner__name=name, status="pending_pickup"
                ).count(),
                "in_transit": Order.objects.filter(
                    user=user, logistic_partner__name=name, status="in_transit"
                ).count(),
                "delivered": Order.objects.filter(
                    user=user, logistic_partner__name=name, status="delivered"
                ).count(),
                "rto": Order.objects.filter(
                    user=user, logistic_partner__name=name, status="rto"
                ).count(),
            }
            cn = courier_status[name.lower()]
            cn["delivered"] = (
                f"{cn['delivered']} ({int((cn['delivered'] / cn['total']) * 100)})"
            )

        # Date wise summary (last 7 days)
        date_wise_summary = {}
        for i in range(7):
            day = today - timedelta(days=i)
            key = day.strftime("%d_%b").lower()
            orders_day = Order.objects.filter(user=user, created_at__date=day)
            date_wise_summary[key] = {
                "no_of_packets": orders_day.count(),
                "pickup_pending": orders_day.filter(status="pending_pickup").count(),
                "in_transit": orders_day.filter(status="in_transit").count(),
                "delivered": orders_day.filter(status="delivered").count(),
                "rto": orders_day.filter(status="rto").count(),
            }

        def get_category_data():
            """Get sales distribution by courier"""
            orders = (
                orders_queryset.filter(
                    created_at__date__gte=first_day_this_month,
                    created_at__date__lte=today,
                )
                .values("logistic_partner__name")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            courier_data = {}
            total = 0

            for order in orders:
                courier_name = order["logistic_partner__name"] or "Unknown"
                courier_data[courier_name] = order["count"]
                total += order["count"]

            # Convert to percentages for chart
            labels = list(courier_data.keys())
            series = [courier_data[label] for label in labels]

            return {"series": series, "labels": labels, "total": total}

        zone_counts = (
            orders_queryset.filter(
                created_at__date__gte=first_day_this_month,
                created_at__date__lte=today,
            )
            .values("json__detected_zone")
            .annotate(count=Count("id"))
            .order_by("json__detected_zone")
        )
        zone_wise_load = {
            "series": [item["count"] for item in zone_counts],
            "labels": [
                item["json__detected_zone"] or "Unknown" for item in zone_counts
            ],
        }
        zone_wise_load["total"] = sum(zone_wise_load["series"])
        return JsonResponse(
            {
                "status": "success",
                "last_updated": timezone.localtime().strftime("%Y-%m-%d %I:%M%p"),
                "data": {
                    "statistics": statistics,
                    "sales_by_category": get_category_data(),
                    "zone_wise_load": zone_wise_load,
                    "current_month_data": current_month_data,
                    "last_month_data": last_month_data,
                    "state_wise_load": state_wise_load,
                    "courier_wise_status": courier_status,
                    "date_wise_summary": date_wise_summary,
                },
            }
        )
    return render(request, "user_panel/analytics.dj")


@user_required
def kyc(request):
    """View for KYC details submission and update."""
    if request.method == "POST":
        data = request.POST
        file = request.FILES
        user = request.user

        kyc = user.get_kyc()
        if kyc and kyc.is_kyc_verified:
            messages.info(request, "Please contact your KAM")
            return redirect("user_panel:kyc")

        if data.get("agree_terms") != "on":
            messages.error(request, "You must agree to the terms and conditions.")
            return redirect("user_panel:kyc")

        # ------ KYC Tab ------
        user.full_name = data.get("name", user.full_name).strip()
        user.company_name = data.get("company_name", user.company_name).strip()
        user.contact_no = data.get("phone_number", user.contact_no).strip()
        user.gstin = data.get("gst_number", user.gstin).strip()

        user.email = data.get("email", user.email).strip()

        user.address = data.get("full_address", user.address).strip()
        user.pin_code = data.get("pin_code", user.pin_code).strip()
        user.city = data.get("city", user.city).strip()
        user.state = data.get("state", user.state).strip()
        user.country = data.get("country", user.country).strip()

        if aadhaar_card := file.get("aadhaar_card", user.aadhaar_card):
            user.aadhaar_card = aadhaar_card

        if gst_certificate := file.get("gst_certificate", user.gst_certificate):
            user.gst_certificate = gst_certificate

        if pan_card := file.get("pan_card", user.pan_card):
            user.pan_card = pan_card

        # ------ Finance Details ------
        user.bank_name = data.get("bank_name", user.bank_name).strip()
        user.bank_account_number = data.get(
            "bank_account_number", user.bank_account_number
        ).strip()
        user.bank_account_ifsc = data.get(
            "bank_account_ifsc", user.bank_account_ifsc
        ).strip()
        user.bank_account_type = data.get(
            "bank_account_type", user.bank_account_type
        ).strip()

        user.cancel_cheque = file.get("cheque", user.cancel_cheque)

        kyc.is_agreement_accepted = True

        try:
            kyc.submit_kyc()
        except Exception as e:
            logger.exception("Error While Submitting KYC Form")
            messages.error(request, f"Error while submitting kyc: {e}")
            return render(request, "user_panel/setting/kyc.dj")

        try:
            user.save()
        except Exception as e:
            logger.exception("Error while saving user info while saving kyc form")
            messages.error(request, f"Error while saving user info: {e}")
            return render(request, "user_panel/setting/kyc.dj")

        messages.success(request, "KYC details submitted successfully.")
    return render(request, "user_panel/setting/kyc.dj")


@user_required
def billing(request):
    return render(request, "user_panel/billing.dj")


# @user_required
# def reports(request):
#     data = request.GET
#     date_filter = data.get("date_filter", "last_7_days")

#     today = now().date()

#     DATE_RANGES = {
#         "today": (today, today),
#         "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
#         "last_7_days": (today - timedelta(days=7), today),
#         "last_30_days": (today - timedelta(days=30), today),
#         "last_year": (today - timedelta(days=365), today),
#         "lifetime": (None, None),
#     }

#     start_date, end_date = DATE_RANGES.get(date_filter, DATE_RANGES["last_7_days"])

#     orders = Order.objects.filter(user=request.user)

#     if start_date and end_date:
#         orders = orders.filter(order_date__date__range=(start_date, end_date))

#     # =====================================================
#     # 1. SHIPMENT SUMMARY (DATE WISE)
#     # =====================================================
#     shipment_summary_map = defaultdict(lambda: {"total": 0, "prepaid": 0, "cod": 0})

#     for o in orders.exclude(status__in=["cancelled", "ready_to_ship"]):
#         try:
#             booked_at = o.shipment.booked_at
#             date_key = booked_at.date().strftime("%d %b %Y")
#             shipment_summary_map[date_key]["total"] += 1
#             if o.payment.method == "cod":
#                 shipment_summary_map[date_key]["cod"] += 1
#             else:
#                 shipment_summary_map[date_key]["prepaid"] += 1
#         except:
#             pass

#     shipment_summary = [
#         [k, v["total"], v["prepaid"], v["cod"]] for k, v in shipment_summary_map.items()
#     ]

#     # =====================================================
#     # 2. DAILY SUMMARY
#     # =====================================================
#     courier_summary = (
#         orders.filter(shipment__booked_at__date=now().date())
#         .values("logistic_partner__name")
#         .annotate(
#             orders=Count("id", exclude=Q(status__in=["cancelled", "read_to_ship"])),
#             delivered=Count("id", filter=Q(status="delivered")),
#             rto=Count("id", filter=Q(status__startswith="rto")),
#         )
#     )

#     daily_summary = []
#     for c in courier_summary:
#         if c["logistic_partner__name"]:
#             daily_summary.append(
#                 [
#                     c["logistic_partner__name"] or "Unassigned",
#                     c["orders"],
#                     c["delivered"],
#                     c["rto"],
#                 ]
#             )

#     # =====================================================
#     # 3. STATE WISE SUMMARY
#     # =====================================================
#     state_summary_qs = orders.values("shipping_address__state").annotate(
#         orders=Count("id"),
#         revenue=Sum("total_amount"),
#     )

#     state_wise_summary = [
#         [s["shipping_address__state"] or "Unknown", s["orders"], s["revenue"] or 0]
#         for s in state_summary_qs
#     ]

#     # =====================================================
#     # 4. PRODUCT WISE SUMMARY
#     # =====================================================
#     product_summary_qs = (
#         OrderItem.objects.filter(order__in=orders)
#         .annotate(normalized_name=Lower(Trim("product__name")))
#         .values("normalized_name")
#         .annotate(
#             qty=Sum("quantity"),
#             revenue=Sum("total_price"),
#             sku_code=Min("sku_code"),
#         )
#     )

#     product_wise_summary = [
#         [p["sku_code"], p["normalized_name"].title(), p["qty"], p["revenue"]]
#         for p in product_summary_qs
#     ]

#     # =====================================================
#     # 5. COURIER PERFORMANCE SUMMARY
#     # =====================================================
#     courier_perf = orders.values("logistic_partner__name").annotate(
#         orders=Count("id", exclude=Q(status__in=["cancelled", "ready_to_ship"])),
#         delivered=Count("id", filter=Q(status="delivered")),
#     )

#     courier_wise_summary = []
#     for c in courier_perf:
#         success = round((c["delivered"] / c["orders"]) * 100, 2) if c["orders"] else 0
#         if c["logistic_partner__name"]:
#             courier_wise_summary.append(
#                 [c["logistic_partner__name"], c["orders"], "-", success]
#             )

#     # =====================================================
#     # 6. CHANNEL WISE SUMMARY
#     # =====================================================
#     channel_summary_qs = orders.values("channel").annotate(
#         orders=Count("id"),
#         revenue=Sum("total_amount"),
#     )

#     channel_wise_summary = [
#         [c["channel"], c["orders"], c["revenue"] or 0] for c in channel_summary_qs
#     ]

#     # =====================================================
#     # 7. ZONE WISE SUMMARY (FROM RATE CARD JSON)
#     # =====================================================
#     zone_map = defaultdict(lambda: {"orders": 0, "cod": 0})

#     for o in orders.select_related("payment"):
#         zone = o.json.get("rate_card_details", {}).get("zone", "Unknown")
#         zone_map[zone]["orders"] += 1
#         if o.payment.method == "cod":
#             zone_map[zone]["cod"] += 1

#     zone_wise_summary = [
#         [
#             z,
#             v["orders"],
#             round((v["cod"] / v["orders"]) * 100, 2) if v["orders"] else 0,
#         ]
#         for z, v in zone_map.items()
#     ]

#     # =====================================================
#     # 8. NDR REASON REPORT (BASIC VERSION)
#     # =====================================================
#     ndr_orders = orders.filter(status="ndr")

#     ndr_reason_map = defaultdict(int)
#     for o in ndr_orders:
#         reason = o.json.get("ndr_reason", "Others")
#         ndr_reason_map[reason] += 1

#     total_ndr = sum(ndr_reason_map.values()) or 1

#     ndr_reason_report = [
#         [k, v, round((v / total_ndr) * 100, 2)] for k, v in ndr_reason_map.items()
#     ]

#     ctx = {
#         "date_filter": date_filter,
#         "shipment_summary": shipment_summary,
#         "daily_summary": daily_summary,
#         "state_wise_summary": state_wise_summary,
#         "product_wise_summary": product_wise_summary,
#         "courier_wise_summary": courier_wise_summary,
#         "channel_wise_summary": channel_wise_summary,
#         "zone_wise_summary": zone_wise_summary,
#         "ndr_reason_report": ndr_reason_report,
#     }

#     return render(request, "user_panel/mis.dj", ctx)


@user_required
def weight_discrepancies(request):
    return render(request, "user_panel/weight_discrepancies.dj")


@user_required
def ndr(request):
    """View for NDR (Non-Delivery Report) management."""
    if request.method == "POST":
        data = request.POST

        order_id = data.get("order_id", "").strip()
        remark = data.get("remark", "").strip()
        action = data.get("action", "").strip()
        if action not in [
            "rto",
            "re_attempt",
            "hold_24hrs",
            "update_address",
            "update_phone",
        ]:
            messages.error(request, "Invalid action.")
            return redirect("user_panel:ndr")

        order = Order.objects.filter(id=order_id, user=request.user).first()
        if not order:
            messages.error(request, "Order not found.")
            return redirect("user_panel:ndr")

        if action == "update_address":
            pass
        elif action == "update_phone":
            pass
        elif action == "re_attempt":
            pass
        elif action == "hold_24hrs":
            pass
        elif action == "rto":
            pass

        messages.success(request, "NDR recorded successfully.")
        return redirect("user_panel:ndr")

    # Checkbox CHANNEL ORDER ID DATE CUSTOMER PRODUCTS QTY AMT STATUS ACTION
    orders = Order.objects.all()[:5]
    # orders = Order.objects.filter(status="ndr", user=request.user)[:5]
    orders_list: list[list] = []
    for order in orders:
        prep_data = [
            "",
            order.get_channel_display(),
            str(order.id),
            order.created_at.strftime("%d %b %Y"),
            order.shipping_address.name if order.shipping_address else "N/A",
            "Product A, Product B",
            "2",
            f"{float(order.total_amount):.2f}",
            order.get_status_display(),
        ]
        prep_data.append(
            f"<button class='action-btn bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700' data-order-id='{order.id}' data-date='{order.created_at.strftime('%Y-%m-%d')}' data-customer='{order.shipping_address.name if order.shipping_address else 'N/A'}'>Take Action</button>"
        )
        orders_list.append(prep_data)
    ctx = {"orders": json.dumps(orders_list), "total_orders": len(orders_list)}

    return render(request, "user_panel/ndr.dj", ctx)


@user_required
def rate_card(request):
    """View to display and filter rate cards."""
    rate_cards = request.user.rate_cards.all()

    mode = request.GET.get("mode")
    weight = request.GET.get("weight")
    search = request.GET.get("q")

    # Search by courier name
    if search:
        rate_cards = rate_cards.filter(courier__name__icontains=search)

    # Convert queryset to list for Python filtering
    rate_cards = list(rate_cards)

    # Filter by mode (from JSONField)
    if mode:
        rate_cards = [
            rc
            for rc in rate_cards
            if mode.lower() in [m.lower() for m in rc.get_available_modes()]
        ]

    # Filter by weight (from JSONField) -> compare as float
    if weight:
        rate_cards = [
            rc
            for rc in rate_cards
            if any(float(w) == float(weight) for w in rc.get_available_weights())
        ]

    return render(
        request, "user_panel/finance/rate_card.dj", {"rate_cards": rate_cards}
    )


@user_required
def shipping_charges(request):
    """
    Display shipping charges for all orders,
    excluding 'ready_to_ship' status.
    """

    orders = (
        Order.objects.filter(user=request.user)
        .select_related("logistic_partner", "user", "payment")
        .exclude(status="ready_to_ship")
        .order_by("-placed_at")
    )

    orders_with_freight = []

    for order in orders:
        payment = order.payment

        freight = freight_gst = rto_total = 0.0

        if payment and payment.price_breakup:
            pb = payment.price_breakup

            base_charge = pb.get("base_charge", 0.0)
            additional_charges = pb.get("additional_charges", 0.0)
            cod_charge = pb.get("cod_charge", 0.0)
            gst_amount = pb.get("gst_amount", 0.0)
            rto_charges = pb.get("rto_charges", 0.0)
            rto_gst_amount = pb.get("rto_gst_amount", 0.0)

            freight = base_charge + additional_charges + cod_charge
            freight_gst = gst_amount

            if order.status.startswith("rto"):
                rto_total = round(rto_charges + rto_gst_amount, 2)

        orders_with_freight.append(
            {
                "order": order,
                "freight": freight,
                "freight_gst": freight_gst,
                "total_freight": freight + freight_gst + rto_total,
                "rto_charges": rto_total,
            }
        )

    return render(
        request,
        "user_panel/finance/shipping_charges.dj",
        {"orders_with_freight": orders_with_freight},
    )


@user_required
def cod_remittance(request):
    """View for COD remittance details."""
    if request.method != "GET":
        messages.error(request, "Invalid request method.")
        return redirect("user_panel:cod-remittance")

    query = request.GET.get("q")

    ctx = CODRemittance.get_user_remittance_dashboard(request.user, query=query)

    return render(request, "user_panel/finance/cod_remittance.dj", ctx)


@user_required
def download_cod_remittance_file(request, cod_remittance_id: int):
    """
    Download COD Remittance CSV (Streamed)

    Generates a CSV file containing all orders linked to a COD remittance.
    The file is streamed directly from database rows to the response,
    avoiding memory overload even for very large datasets.

    CSV Columns
    -----------
    - Remittance ID
    - Order Id
    - Shipped Date
    - Courier
    - AWB
    - Status
    - Delivered Date
    - Order Value
    - Remittance Date
    - UTR

    Performance Characteristics
    ---------------------------
    ✔ Constant memory usage
    ✔ Chunked DB fetching
    ✔ Single optimized query
    ✔ Suitable for 1M+ rows

    Returns
    -------
    StreamingHttpResponse
        CSV file download response.
    """

    # ======================================================
    # FETCH REMITTANCE
    # ======================================================
    try:
        cod_remittance = CODRemittance.objects.only(
            "id",
            "_payout_date",
            "_utr_no",
        ).get(
            id=cod_remittance_id,
            _user=request.user,
        )
    except:
        messages.error(request, "COD remittance not found or access denied.")
        return redirect("user_panel:cod-remittance")

    # try:
    #     file_url = cod_remittance.get_file()

    #     if file_url:
    #         return redirect(cod_remittance._file.url)
    # except:
    #     pass

    # messages.error(request, "File not found")
    # return redirect("user_panel:cod-remittance")
    # ======================================================
    # OPTIMIZED ORDERS QUERY
    # ======================================================
    orders = (
        Order.objects.filter(cod_remittance_id=cod_remittance.id)
        .select_related("shipment", "logistic_partner")
        .only(
            "id",
            "awb_number",
            "total_amount",
            "shipment__shipped_at",
            "shipment__delivered_at",
            "logistic_partner__name",
            "status",
        )
        .iterator(chunk_size=2000)  # tuned chunk size
    )

    # ======================================================
    # STREAMING CSV WRITER
    # ======================================================
    class CSVBuffer:
        """Minimal write buffer used by csv.writer for streaming."""

        def write(self, value):
            return value

    def format_dt(dt):
        """Return Excel-safe datetime string."""
        if not dt:
            return ""
        return localtime(dt).strftime("%Y-%m-%d %H:%M:%S")

    def row_stream():
        """
        Generator yielding CSV rows one-by-one.

        Using generator ensures:
        - no large memory allocation
        - immediate download start
        """
        buffer = CSVBuffer()
        writer = csv.writer(buffer)

        # ---------------- HEADER ----------------
        yield writer.writerow(
            [
                "Remittance ID",
                "Order Id",
                "Shipped Date",
                "Courier",
                "AWB",
                "Status",
                "Delivered Date",
                "Order Value",
                "Remittance Date",
                "UTR",
            ]
        )

        payout_date = cod_remittance._payout_date
        utr = cod_remittance._utr_no

        # ---------------- DATA ROWS ----------------
        for order in orders:
            shipment = getattr(order, "shipment", None)

            yield writer.writerow(
                [
                    cod_remittance.id,
                    order.id,
                    format_dt(getattr(shipment, "shipped_at", None)),
                    getattr(order.logistic_partner, "name", ""),
                    order.awb_number,
                    order.get_status_display(),
                    format_dt(getattr(shipment, "delivered_at", None)),
                    round(float(order.total_amount or 0), 2),
                    payout_date,
                    utr,
                ]
            )

    # ======================================================
    # RESPONSE
    # ======================================================
    response = StreamingHttpResponse(
        row_stream(),
        content_type="text/csv; charset=utf-8",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="cod_remittance_{cod_remittance.id}.csv"'
    )

    return response


@user_required
def all_recharges(request):
    """View for all wallet recharges by the user."""
    recharges = Transaction.objects.filter(
        user=request.user, desc="wallet_recharge"
    ).order_by("-id")

    paginator, page_obj = paginate_queryset(recharges, request.GET)

    return render(
        request,
        "user_panel/finance/all_recharges.dj",
        {
            "page_obj": page_obj,
            "page_size": paginator.per_page,
        },
    )


@user_required
def wallet_history(request):
    # Get all transactions for the logged-in user
    history = Transaction.objects.filter(user=request.user).order_by("-created_at")

    # Get query params with defaults
    try:
        page_size = int(request.GET.get("page_size", 10))  # default 10 items per page
    except:
        page_size = 10

    try:
        page_number = request.GET.get("page", 1)  # default first page
    except:
        page_number = 1

    # Set up pagination
    paginator = Paginator(history, page_size)
    page_obj = paginator.get_page(page_number)

    # Pass paginated data to template
    ctx = {"page_obj": page_obj, "page_size": page_size}
    return render(request, "user_panel/finance/wallet_history.dj", ctx)


@user_required
def invoices(request):
    data = request.GET

    # query params
    page = data.get("page", 1)
    page_size = min(int(data.get("page_size", 20)), 200)  # max limit = 200
    q = data.get("q", "").strip()

    # base queryset
    invoices_qs = Invoice.get_for_a_user(user=request.user)

    # search (example: invoice_no / awb / reference)
    if q:
        invoices_qs = invoices_qs.filter(
            Q(number__icontains=q)
            | Q(id__icontains=q)
            | Q(amount__icontains=q)
            | Q(date__icontains=q)
            | Q(period__icontains=q)
        )

    # pagination
    paginator = Paginator(invoices_qs, page_size)

    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "page_obj": page_obj,
        "page_size": page_size,
        "invoices": page_obj.object_list,
        "q": q,
    }

    return render(
        request,
        "user_panel/finance/invoices.dj",
        context,
    )


@user_required
def courier_rules(request):
    """View to set courier priority rules for the user."""
    if request.method == "POST":
        try:
            courier_ids = request.POST.get("priority", "").split(",")
            selected_couriers = Courier.get_couriers_by_ids(courier_ids)
            CourierPreferenceSequence.create_or_update_preference(
                request.user, selected_couriers
            )
            messages.success(request, "Courier priority updated successfully.")
        except Exception as e:
            logger.error(f"Error updating courier priority: {e}", exc_info=True)
            messages.error(request, "Failed to update courier priority.")

    ctx = {"couriers": CourierPreferenceSequence.get_user_preference(request.user)}

    return render(
        request,
        "user_panel/setting/courier_rules.dj",
        ctx,
    )


@user_required
def label(request):
    ctx = {
        "label_setting": request.user.get_label_setting(),
    }

    return render(request, "user_panel/setting/label.dj", ctx)


@user_required
def invoice(request):
    return render(request, "user_panel/setting/invoice.dj")


@user_required
def mis(request):
    if request.method != "GET":
        return HttpResponse("Invalid Request Method")

    def percentage(value: float, total: float):
        if total == 0:
            return 0
        return round((value / total) * 100, 2)

    order_qs = (
        Order.objects.filter(user=request.user)
        .exclude(status__in=["cancelled", "ready_to_ship"])
        .select_related("logistic_partner", "shipment")
        .prefetch_related("items__product")
    )

    # -----------------------------
    # GET Filters
    # -----------------------------
    data = request.GET
    date_from = data.get("date_from")
    date_to = data.get("date_to")
    method = data.get("method")
    courier = data.get("courier")

    # -----------------------------
    # Date Filter
    # -----------------------------
    try:
        if date_from:
            date_from = make_aware(datetime.strptime(date_from, "%m/%d/%Y"))
            order_qs = order_qs.filter(shipment__booked_at__gte=date_from)

        if date_to:
            date_to = make_aware(datetime.strptime(date_to, "%m/%d/%Y"))
            order_qs = order_qs.filter(shipment__booked_at__lte=date_to)

    except ValueError:
        pass  # Ignore invalid date input safely

    if date_from is None and date_to is None:
        order_qs = order_qs.filter(
            shipment__booked_at__gte=now().date() - timedelta(days=7)
        )

    # -----------------------------
    # Payment Method Filter
    # -----------------------------
    if method and method.lower() != "all":
        order_qs = order_qs.filter(payment__method__iexact=method)

    # -----------------------------
    # Courier Filter
    # -----------------------------
    if courier and courier.isdigit():
        order_qs = order_qs.filter(logistic_partner_id=int(courier))

    # ======================================================
    # DAILY SUMMARY
    # ======================================================
    daily_summary = (
        order_qs.filter(
            shipment__isnull=False,
            shipment__booked_at__isnull=False,
        )
        .annotate(date=TruncDate("shipment__booked_at"))
        .values("date")
        .annotate(
            shipment_picked=Count("id", filter=Q(status="pending_pickup")),
            in_transit=Count("id", filter=Q(status="in_transit")),
            out_for_delivery=Count("id", filter=Q(status="out_for_delivery")),
            exception=Count("id", filter=Q(status__in=["exception", "ndr", "lost"])),
            delivered=Count("id", filter=Q(status="delivered")),
            rto=Count(
                "id",
                filter=Q(status__startswith="rto") & ~Q(status="rto_delivered"),
            ),
            rto_delivered=Count("id", filter=Q(status="rto_delivered")),
        )
        .order_by("-date")
    )

    daily_summary_data = OrderedDict()

    for d in daily_summary:
        date = d["date"]

        shipment_picked = d["shipment_picked"]
        in_transit = d["in_transit"]
        out_for_delivery = d["out_for_delivery"]
        exception = d["exception"]
        delivered = d["delivered"]
        rto = d["rto"]
        rto_delivered = d["rto_delivered"]

        total = (
            shipment_picked
            + in_transit
            + out_for_delivery
            + exception
            + delivered
            + rto
            + rto_delivered
        )

        # skip empty day
        if total == 0:
            continue

        formatted_date = date.strftime("%b %d, %Y")

        daily_summary_data[formatted_date] = [
            total,
            {
                "Pending Pickup": {
                    "current": shipment_picked,
                    "percentage": percentage(shipment_picked, total),
                },
                "In Transit": {
                    "current": in_transit,
                    "percentage": percentage(in_transit, total),
                },
                "Out For Delivery": {
                    "current": out_for_delivery,
                    "percentage": percentage(out_for_delivery, total),
                },
                "Delivered": {
                    "current": delivered,
                    "percentage": percentage(delivered, total),
                },
                "Exception": {
                    "current": exception,
                    "percentage": percentage(exception, total),
                },
                "RTO": {
                    "current": rto,
                    "percentage": percentage(rto, total),
                },
                "RTO Delivered": {
                    "current": rto_delivered,
                    "percentage": percentage(rto_delivered, total),
                },
            },
        ]

    # ======================================================
    # TOP NDR REASON
    # ======================================================
    # NDR is not build yet
    # ndr_qs = (
    #     order_qs.filter(status="ndr")
    #     .values("json__ndr_reason")
    #     .annotate(
    #         shipment_picked=Count("id", filter=Q(status="pending_pickup")),
    #         in_transit=Count("id", filter=Q(status="in_transit")),
    #         exception=Count("id", filter=Q(status__in=["exception", "ndr"])),
    #         delivered=Count("id", filter=Q(status="delivered")),
    #         rto_in_transit=Count("id", filter=Q(status="rto_in_transit")),
    #         rto_delivered=Count("id", filter=Q(status="rto_delivered")),
    #     )
    #     .order_by("-exception")[:10]
    # )

    # top_ndr_reason_data = [
    #     [
    #         n.get("json__ndr_reason") or "Unknown",
    #         n["shipment_picked"],
    #         n["in_transit"],
    #         n["exception"],
    #         n["delivered"],
    #         n["rto_in_transit"],
    #         n["rto_delivered"],
    #     ]
    #     for n in ndr_qs
    # ]

    # ======================================================
    # PRODUCT WISE SUMMARY
    # ======================================================
    product_summary = (
        order_qs.values("items__product__name")
        .annotate(
            shipment_picked=Count("id", filter=Q(status="pending_pickup")),
            in_transit=Count("id", filter=Q(status="in_transit")),
            exception=Count("id", filter=Q(status__in=["exception", "ndr"])),
            delivered=Count("id", filter=Q(status="delivered")),
            rto_in_transit=Count("id", filter=Q(status="rto_in_transit")),
            rto_delivered=Count("id", filter=Q(status="rto_delivered")),
        )
        .order_by("-delivered")
    )

    product_wise_summary_data = [
        [
            p["items__product__name"],
            p["shipment_picked"],
            p["in_transit"],
            p["exception"],
            p["delivered"],
            p["rto_in_transit"],
            p["rto_delivered"],
        ]
        for p in product_summary
    ]

    # ======================================================
    # COURIER WISE SUMMARY
    # ======================================================
    courier_summary = (
        order_qs.filter(logistic_partner__isnull=False)
        .values("logistic_partner__name")
        .annotate(
            total_shipped=Count("id"),
            booked=Count("id", filter=Q(status="ready_to_ship")),
            pending_pickup=Count("id", filter=Q(status="pending_pickup")),
            in_transit=Count("id", filter=Q(status="in_transit")),
            delivered=Count("id", filter=Q(status="delivered")),
            rto=Count("id", filter=Q(status__startswith="rto")),
        )
        .order_by("-total_shipped")
    )

    courier_wise_summary_data = [
        [
            c.get("logistic_partner__name") or "Unknown",
            c["total_shipped"],
            c["booked"],
            c["pending_pickup"],
            c["in_transit"],
            c["delivered"],
            c["rto"],
        ]
        for c in courier_summary
    ]

    ctx = {
        "daily_summary": daily_summary_data,
        "top_ndr_reason": [],
        "product_wise_summary": product_wise_summary_data,
        "courier_wise_summary": courier_wise_summary_data,
        "couriers_available": dict(
            Order.objects.filter(user=request.user, logistic_partner__isnull=False)
            .values_list("logistic_partner__id", "logistic_partner__name")
            .distinct()
        ),
    }

    return render(request, "user_panel/mis.dj", ctx)


@user_required
def printer(request):
    label_setting = request.user.get_label_setting()

    if request.method == "POST":
        selected_size = request.POST.get("label_page_size", "4x6").strip().lower()
        allowed_sizes = {"a4", "a4_single", "4x6", "3x5"}
        label_setting.label_page_size = (
            selected_size if selected_size in allowed_sizes else "4x6"
        )
        label_setting.save(update_fields=["label_page_size", "updated_at"])
        messages.success(request, "Printer setting updated successfully.")
        return redirect("user_panel:printer")

    return render(
        request,
        "user_panel/setting/printer.dj",
        {"label_setting": label_setting},
    )


@user_required
def view_label(request, order_id: int):
    ctx = {
        "order": Order.objects.filter(id=order_id, user=request.user).first(),
    }
    return render(request, "user_panel/view_label.dj", ctx)


@user_required
def view_invoice(request, order_id: int):
    ctx = {
        "order": Order.objects.filter(id=order_id, user=request.user).first(),
    }
    return render(request, "user_panel/view_invoice.dj", ctx)


@user_required
def ats_label_proxy(request):
    label_url = (request.GET.get("url") or "").strip()
    if not label_url:
        return JsonResponse({"error": "Missing ATS label url."}, status=400)

    parsed = urlparse(label_url)
    if parsed.scheme not in ("http", "https"):
        return JsonResponse({"error": "Invalid ATS label url."}, status=400)

    # Restrict proxy usage to known ATS/Fship label hosts only.
    allowed_hosts = {"manifest.fship.in", "capi.fship.in", "storage.googleapis.com"}
    if parsed.netloc.lower() not in allowed_hosts:
        return JsonResponse({"error": "ATS label host not allowed."}, status=403)

    try:
        resp = requests.get(label_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(
            "ATS proxy fetch failed for url=%s: %s", label_url, str(e), exc_info=True
        )
        return JsonResponse({"error": "Failed to fetch ATS label."}, status=502)

    response = HttpResponse(resp.content, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="ats_label.pdf"'
    return response


@user_required
def labels_api(request):
    raw_order_ids = request.GET.get("order_id", "")
    raw_awbs = request.GET.get("awb", "")

    order_ids = [int(x) for x in re.findall(r"\d+", raw_order_ids)]
    awbs = [x.strip() for x in raw_awbs.split(",") if x.strip()]

    if not order_ids and not awbs:
        return JsonResponse({"error": "Provide order_id or awb."}, status=400)

    orders = (
        Order.objects.filter(
            user=request.user,
            status__in=[
                "ready_to_ship",
                "processing",
                "pending_pickup",
                "in_transit",
                "out_for_delivery",
                "delivered",
                "rto",
                "rto_pending_pickup",
                "rto_in_transit",
                "rto_out_for_deliivery",
                "rto_delivered",
                "ndr",
            ],
        )
        .select_related(
            "shipping_address", "shipment", "payment", "hub", "logistic_partner"
        )
        .prefetch_related("items", "items__product")
    )

    if order_ids:
        orders = orders.filter(id__in=order_ids)
    else:
        orders = orders.filter(awb_number__in=awbs)

    label_setting = request.user.get_label_setting()
    settings_payload = {
        "show_logo": label_setting.show_logo,
        "show_support_info": label_setting.show_support_info,
        "support_phone": label_setting.support_phone or "",
        "support_email": label_setting.support_email or "",
        "show_customer_mobile": label_setting.show_customer_mobile,
        "show_pickup_address": label_setting.show_pickup_address,
        "show_discount": label_setting.show_discount,
        "show_powered_by": label_setting.show_powered_by,
        "show_product": label_setting.show_product,
        "show_total_amount": label_setting.show_total_amount,
        "show_weight": label_setting.show_weight,
        "show_dimension": label_setting.show_dimension,
        "label_page_size": label_setting.label_page_size,
        "ats_label_proxy_url": reverse("user_panel:ats-label-proxy"),
    }

    orders = list(orders)
    if not orders:
        return JsonResponse({"labels": [], "settings": settings_payload}, status=200)

    ats_orders = [
        o
        for o in orders
        if o.logistic_partner
        and "_ats_" in ((o.logistic_partner.abbreviation or "").strip().lower())
    ]
    ats_urls = []
    if ats_orders:
        urls, err = _generate_amazon_shipment_labels_url(ats_orders, request)
        if err:
            logger.error(
                "ATS label generation error in labels_api: %s", err, exc_info=True
            )
            return JsonResponse(
                {"error": f"Failed to generate ATS labels: {err}"}, status=502
            )
        ats_urls = urls or []
    ats_url_map = {
        order.id: ats_urls[idx] if idx < len(ats_urls) else None
        for idx, order in enumerate(ats_orders)
    }

    def safe_attr(obj, attr, default=""):
        if obj is None:
            return default
        return getattr(obj, attr, default)

    labels = []
    for order in orders:
        shipping = order.shipping_address
        shipment = getattr(order, "shipment", None)
        payment = getattr(order, "payment", None)
        hub = order.hub

        products = []
        for item in order.items.all():
            products.append(
                {
                    "name": safe_attr(item.product, "name", ""),
                    "sku": safe_attr(item.product, "sku", ""),
                    "hsn": safe_attr(
                        item.product, "hsn_code", safe_attr(item, "hsn_code", "")
                    ),
                    "qty": item.quantity,
                    "price": item.unit_price,
                    "amount": item.total_price,
                    "discount": safe_attr(payment, "discount", 0),
                }
            )

        labels.append(
            {
                "id": order.id,
                "awb": order.awb_number,
                "order_number": order.order_number,
                "order_date": (
                    timezone.localtime(order.order_date).strftime("%b %d, %Y")
                    if order.order_date
                    else ""
                ),
                "customer_name": safe_attr(shipping, "name", ""),
                "company_name": safe_attr(shipping, "company_name", ""),
                "customer_phone": safe_attr(shipping, "phone", ""),
                "line1": safe_attr(shipping, "line1", ""),
                "line2": safe_attr(shipping, "line2", ""),
                "city": safe_attr(shipping, "city", ""),
                "state": safe_attr(shipping, "state", ""),
                "country": safe_attr(shipping, "country", ""),
                "pincode": safe_attr(
                    shipping, "pincode", safe_attr(shipping, "pin_code", "")
                ),
                "courier": safe_attr(order.logistic_partner, "name", ""),
                "weight": safe_attr(shipment, "package_weight_kg", ""),
                "length": safe_attr(shipment, "package_length_cm", ""),
                "width": safe_attr(shipment, "package_width_cm", ""),
                "height": safe_attr(shipment, "package_height_cm", ""),
                "payment_mode": safe_attr(payment, "method", "").upper(),
                "discount": safe_attr(payment, "discount", 0),
                "total_amount": order.total_amount,
                "hub_name": safe_attr(hub, "name", ""),
                "hub_line1": safe_attr(hub, "address_line1", ""),
                "hub_city": safe_attr(hub, "city", ""),
                "hub_state": safe_attr(hub, "state", ""),
                "hub_country": safe_attr(hub, "country", ""),
                "hub_pincode": safe_attr(hub, "pincode", ""),
                "hub_phone": safe_attr(hub, "phone", ""),
                "logo_url": (
                    request.build_absolute_uri(label_setting.logo.url)
                    if label_setting.show_logo and label_setting.logo
                    else ""
                ),
                "support_info": (
                    f"{label_setting.support_phone}"
                    + (
                        f" | {label_setting.support_email}"
                        if label_setting.support_email
                        else ""
                    )
                    if label_setting.show_support_info
                    else ""
                ),
                "products": products,
                "is_amazon": order.id in ats_url_map,
                "amazon_label_url": ats_url_map.get(order.id),
            }
        )

    return JsonResponse({"settings": settings_payload, "labels": labels})


def _generate_amazon_shipment_labels_url(
    orders: list[Order], request
) -> tuple[Optional[list[str]], Optional[any]]:
    """
    Generate Amazon shipment label URLs grouped by courier / logistic partner.
    """

    if not orders:
        return [], None

    urls: list[str] = []
    courier_order_map = defaultdict(list)

    for order in orders:
        if not order.logistic_partner:
            return None, f"Order {order.id} has no logistic partner assigned"
        courier_order_map[order.logistic_partner].append(order)

    ats_module_map = {
        "fs_ats_500": "fship_integration.fship_amazon_500gm",
        "fs_ats_1kg": "fship_integration.fship_amazon_1kg",
        "fs_ats_2kg": "fship_integration.fship_amazon_2kg",
        "fs_ats_5kg": "fship_integration.fship_amazon_5kg",
        "fs_ats_10kg": "fship_integration.fship_amazon_10kg",
    }

    for courier, courier_orders in courier_order_map.items():
        try:
            courier_abbr = (courier.abbreviation or "").strip().lower()
            if courier_abbr in ats_module_map:
                ats_handler = importlib.import_module(ats_module_map[courier_abbr])
            else:
                ats_handler = get_courier_handler(courier)

            if not hasattr(ats_handler, "generate_label"):
                return (
                    None,
                    f"Courier handler for {courier.name} does not implement generate_label",
                )

            err, url = ats_handler.generate_label(courier_orders)

            if err:
                return (
                    None,
                    f"Label generation failed for courier {courier.name}: {url}",
                )

            if not url:
                return None, f"No label URL returned for courier {courier.name}"

            if isinstance(url, list):
                urls.extend(url)
            else:
                urls.append(url)

        except Exception as e:
            logger.exception("Got exception")
            return None, f"Unexpected error for courier {courier.name}: {str(e)}"

    return urls, None


def _label_pdf_template_table_context(label_page_size):
    """Row cap and truncatechars length for label HTML (align with label_client_pdf.js)."""
    lp = (label_page_size or "4x6").strip().lower()
    if lp == "a4_single":
        return {"label_product_row_cap": 4, "label_product_name_max": 11}
    if lp == "a4":
        return {"label_product_row_cap": 4, "label_product_name_max": 11}
    if lp == "3x5":
        return {"label_product_row_cap": 3, "label_product_name_max": 9}
    return {"label_product_row_cap": 6, "label_product_name_max": 14}


def _generate_amazon_shipment_labels_url_old(
    orders: list[Order], request
) -> tuple[Optional[list[str]], Optional[any]]:
    """
    Generate Amazon shipment label URLs grouped by courier / logistic partner.
    """

    if not orders:
        return [], None

    urls: list[str] = []
    courier_order_map = defaultdict(list)

    for order in orders:
        if not order.logistic_partner:
            return None, f"Order {order.id} has no logistic partner assigned"
        courier_order_map[order.logistic_partner].append(order)

    for courier, courier_orders in courier_order_map.items():
        try:
            ats_handler = get_courier_handler(courier)
            err, url = ats_handler.generate_label(courier_orders)

            if err:
                return (
                    None,
                    f"Label generation failed for courier {courier.name}: {err}",
                )

            if not url:
                return None, f"No label URL returned for courier {courier.name}"

            if isinstance(url, list):
                urls.extend(url)
            else:
                urls.append(url)

        except Exception as e:
            logger.exception("Got exception")
            return None, f"Unexpected error for courier {courier.name}: {str(e)}"

    return urls, None


@user_required
def download_label_old(request):
    """
    Produces a merged PDF with one 100mm x 150mm label per page.
    Includes ATS (Amazon) labels if present.
    """

    if request.method != "GET":
        messages.error(request, "Invalid request method.")
        return redirect("user_panel:dashboard")

    raw_ids = request.GET.get("order_id", "")
    if not raw_ids:
        messages.error(request, "At least one order must be selected.")
        return redirect("user_panel:dashboard")

    import re

    order_ids = [int(x) for x in re.findall(r"\d+", raw_ids)]
    if not order_ids:
        messages.error(request, "No valid order IDs provided.")
        return redirect("user_panel:dashboard")

    MAX_LIMIT = getattr(settings, "MAX_ORDER_DOWNLOAD_LIMIT", 100)
    if len(order_ids) > MAX_LIMIT:
        messages.error(request, f"You can download up to {MAX_LIMIT} labels at once.")
        return redirect("user_panel:dashboard")

    orders = (
        Order.objects.filter(
            id__in=order_ids,
            user=request.user,
            status__in=["pending_pickup", "in_transit"],
        )
        .select_related(
            "shipping_address", "shipment", "payment", "hub", "logistic_partner"
        )
        .prefetch_related("items", "items__product")
    )
    if not orders:
        messages.warning(request, "No order found for label creation")
        return redirect("user_panel:shipment", "pending_pickup")

    # ---------------- ATS HANDLING ----------------
    ats_orders = orders.filter(logistic_partner__abbreviation__contains="_ats_")
    orders = orders.exclude(id__in=ats_orders)

    logger.debug(f"ATS Orders: {[o.id for o in ats_orders]}")
    logger.debug(f"Non-ATS Orders: {[o.id for o in orders]}")

    ats_pdf_list: list[bytes] = []

    if ats_orders.exists():
        ats_urls, err = _generate_amazon_shipment_labels_url_old(
            list(ats_orders), request
        )

        if err:
            logger.error(f"ATS label generation error: {err}", exc_info=True)
            messages.error(
                request,
                f"Failed to generate Amazon shipment labels. Error: {err}",
            )
            return redirect("user_panel:shipment", "pending_pickup")

        for url in ats_urls:
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                ats_pdf_list.append(resp.content)
            except Exception as e:
                logger.error(f"ATS PDF fetch failed for {url}: {e}", exc_info=True)
                messages.error(
                    request,
                    "Failed to download one or more Amazon shipment labels.",
                )
                return redirect("user_panel:shipment", "pending_pickup")

    # ------------------------------------------------

    if not orders.exists() and not ats_pdf_list:
        messages.error(request, "No matching orders found.")
        return redirect("user_panel:dashboard")

    font_config = FontConfiguration()
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    template_name = "user_panel/label/download_old.dj"

    def merge_pdfs(pdf_list):
        merger = PdfMerger()
        for pdf in pdf_list:
            merger.append(BytesIO(pdf))
        output = BytesIO()
        merger.write(output)
        merger.close()
        return output.getvalue()

    # ✅ FIX: ATS ONLY (NO IDIOTSHIP ORDERS → NO BLANK PAGE)
    if not orders.exists() and ats_pdf_list:
        final_pdf = merge_pdfs(ats_pdf_list)
        response = HttpResponse(final_pdf, content_type="application/pdf")
        filename = f"ats_labels_{timestamp}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(final_pdf)
        return response

    # ---------------- SINGLE NON-ATS ORDER ----------------
    if orders.count() == 1:
        order = orders.first()

        html_fragment = render_to_string(
            template_name,
            {
                "order": order,
                "STATIC_URL": settings.STATIC_URL,
                "MEDIA_URL": settings.MEDIA_URL,
                "request": request,
            },
        )

        try:
            label_pdf = HTML(
                string=html_fragment, base_url=request.build_absolute_uri("/")
            ).write_pdf(
                font_config=font_config,
                optimize_size=("images", "fonts"),
                presentational_hints=True,
            )

            pdfs = []
            if ats_pdf_list:
                pdfs.extend(ats_pdf_list)
            pdfs.append(label_pdf)

            final_pdf = merge_pdfs(pdfs)

            response = HttpResponse(final_pdf, content_type="application/pdf")
            filename = f"label_{order.order_number}_{timestamp}.pdf".replace("/", "_")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = len(final_pdf)
            return response

        except Exception as e:
            logger.error(f"Single label PDF error: {e}", exc_info=True)
            messages.error(request, "Failed to generate label.")
            return redirect("user_panel:dashboard")

    # ---------------- MULTIPLE NON-ATS ORDERS ----------------
    try:
        fragments = []
        first_css = None

        for i, order in enumerate(orders):
            frag = render_to_string(
                template_name,
                {
                    "order": order,
                    "STATIC_URL": settings.STATIC_URL,
                    "MEDIA_URL": settings.MEDIA_URL,
                    "request": request,
                },
            )

            if i == 0:
                m = re.search(r"(?s)<style[^>]*>(.*?)</style>", frag)
                if m:
                    first_css = m.group(1).strip()

            frag = re.sub(r"(?s)<style[^>]*>.*?</style>", "", frag)
            frag = re.sub(r"(?s)<script[^>]*>.*?</script>", "", frag)
            frag = re.sub(r"(?i)</?html[^>]*>", "", frag)
            frag = re.sub(r"(?i)</?head[^>]*>", "", frag)
            frag = re.sub(r"(?i)</?body[^>]*>", "", frag)

            fragments.append(f'<div class="label-page">{frag.strip()}</div>')

        page_css = """
        @page { size: 100mm 150mm; margin: 0; }
        .label-page {
            width: 100mm;
            height: 150mm;
            page-break-after: always;
            overflow: hidden;
        }
        .label-page:last-child { page-break-after: auto; }
        html, body { margin: 0; padding: 0; background: white; }
        body { font-family: Arial, Helvetica, sans-serif; font-size: 8px; }
        img { max-width: 100%; height: auto; display: block; }
        """

        combined_css = (first_css + page_css) if first_css else page_css

        combined_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{combined_css}</style>
</head>
<body>
{''.join(fragments)}
</body>
</html>
"""

        label_pdf = HTML(
            string=combined_html, base_url=request.build_absolute_uri("/")
        ).write_pdf(
            font_config=font_config,
            optimize_size=("images", "fonts"),
            presentational_hints=True,
        )

        pdfs = []
        if ats_pdf_list:
            pdfs.extend(ats_pdf_list)
        pdfs.append(label_pdf)

        final_pdf = merge_pdfs(pdfs)

        response = HttpResponse(final_pdf, content_type="application/pdf")
        filename = f"labels_{timestamp}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(final_pdf)
        return response

    except Exception as e:
        logger.error(f"Bulk label PDF error: {e}", exc_info=True)
        messages.error(request, "Failed to generate labels.")
        return redirect("user_panel:dashboard")


@user_required
def download_label(request):
    """
    Produces a merged PDF with one 100mm x 150mm label per page.
    Includes ATS (Amazon) labels if present.
    """

    if request.method != "GET":
        messages.error(request, "Invalid request method.")
        return redirect("user_panel:dashboard")

    raw_ids = request.GET.get("order_id", "")
    if not raw_ids:
        messages.error(request, "At least one order must be selected.")
        return redirect("user_panel:dashboard")

    import re

    order_ids = [int(x) for x in re.findall(r"\d+", raw_ids)]
    if not order_ids:
        messages.error(request, "No valid order IDs provided.")
        return redirect("user_panel:dashboard")

    MAX_LIMIT = getattr(settings, "MAX_ORDER_DOWNLOAD_LIMIT", 100)
    if len(order_ids) > MAX_LIMIT:
        messages.error(request, f"You can download up to {MAX_LIMIT} labels at once.")
        return redirect("user_panel:dashboard")

    orders = (
        Order.objects.filter(
            id__in=order_ids,
            user=request.user,
            status__in=["pending_pickup", "in_transit"],
        )
        .select_related(
            "shipping_address", "shipment", "payment", "hub", "logistic_partner"
        )
        .prefetch_related("items", "items__product")
    )
    if not orders:
        messages.warning(request, "No order found for label creation")
        return redirect("user_panel:shipment", "pending_pickup")

    # ---------------- ATS HANDLING ----------------
    ats_orders = orders.filter(logistic_partner__abbreviation__contains="_ats_")
    orders = orders.exclude(id__in=ats_orders)

    logger.debug(f"ATS Orders: {[o.id for o in ats_orders]}")
    logger.debug(f"Non-ATS Orders: {[o.id for o in orders]}")

    ats_pdf_list: list[bytes] = []

    if ats_orders.exists():
        ats_urls, err = _generate_amazon_shipment_labels_url(list(ats_orders), request)

        if err:
            logger.error(f"ATS label generation error: {err}", exc_info=True)
            messages.error(
                request,
                f"Failed to generate Amazon shipment labels. Error: {err}",
            )
            return redirect("user_panel:shipment", "pending_pickup")

        def fetch_pdf(idx_url: tuple[int, str]):
            idx, url = idx_url
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return idx, resp.content

        indexed_urls = [(idx, url) for idx, url in enumerate(ats_urls or []) if url]
        max_workers = min(8, max(1, len(indexed_urls)))
        fetched_pdf_map: dict[int, bytes] = {}

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(fetch_pdf, item) for item in indexed_urls]
                for future in as_completed(futures):
                    idx, pdf_bytes = future.result()
                    fetched_pdf_map[idx] = pdf_bytes
        except Exception as e:
            logger.error(
                "ATS PDF fetch failed during parallel download: %s",
                str(e),
                exc_info=True,
            )
            messages.error(
                request,
                "Failed to download one or more Amazon shipment labels.",
            )
            return redirect("user_panel:shipment", "pending_pickup")

        ats_pdf_list = [fetched_pdf_map[i] for i in sorted(fetched_pdf_map.keys())]

    # ------------------------------------------------

    if not orders.exists() and not ats_pdf_list:
        messages.error(request, "No matching orders found.")
        return redirect("user_panel:dashboard")

    font_config = FontConfiguration()
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    template_name = "user_panel/label/download.dj"
    label_page_size = request.user.get_label_setting().label_page_size
    label_table_ctx = _label_pdf_template_table_context(label_page_size)

    def merge_pdfs(pdf_list):
        merger = PdfMerger()
        for pdf in pdf_list:
            merger.append(BytesIO(pdf))
        output = BytesIO()
        merger.write(output)
        merger.close()
        return output.getvalue()

    # ✅ FIX: ATS ONLY (NO IDIOTSHIP ORDERS → NO BLANK PAGE)
    if not orders.exists() and ats_pdf_list:
        final_pdf = merge_pdfs(ats_pdf_list)
        response = HttpResponse(final_pdf, content_type="application/pdf")
        filename = f"ats_labels_{timestamp}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(final_pdf)
        return response

    # ---------------- SINGLE NON-ATS ORDER ----------------
    if orders.count() == 1:
        order = orders.first()

        html_fragment = render_to_string(
            template_name,
            {
                "order": order,
                "label_page_size": label_page_size,
                "STATIC_URL": settings.STATIC_URL,
                "MEDIA_URL": settings.MEDIA_URL,
                "request": request,
                **label_table_ctx,
            },
        )

        try:
            label_pdf = HTML(
                string=html_fragment, base_url=request.build_absolute_uri("/")
            ).write_pdf(
                font_config=font_config,
                optimize_size=("images", "fonts"),
                presentational_hints=True,
            )

            pdfs = []
            if ats_pdf_list:
                pdfs.extend(ats_pdf_list)
            pdfs.append(label_pdf)

            final_pdf = merge_pdfs(pdfs)

            response = HttpResponse(final_pdf, content_type="application/pdf")
            filename = f"label_{order.order_number}_{timestamp}.pdf".replace("/", "_")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = len(final_pdf)
            return response

        except Exception as e:
            logger.error(f"Single label PDF error: {e}", exc_info=True)
            messages.error(request, "Failed to generate label.")
            return redirect("user_panel:dashboard")

    # ---------------- MULTIPLE NON-ATS ORDERS ----------------
    try:
        fragments = []
        first_css = None

        for i, order in enumerate(orders):
            frag = render_to_string(
                template_name,
                {
                    "order": order,
                    "label_page_size": label_page_size,
                    "STATIC_URL": settings.STATIC_URL,
                    "MEDIA_URL": settings.MEDIA_URL,
                    "request": request,
                    **label_table_ctx,
                },
            )

            if i == 0:
                m = re.search(r"(?s)<style[^>]*>(.*?)</style>", frag)
                if m:
                    first_css = m.group(1).strip()

            frag = re.sub(r"(?s)<style[^>]*>.*?</style>", "", frag)
            frag = re.sub(r"(?s)<script[^>]*>.*?</script>", "", frag)
            frag = re.sub(r"(?i)</?html[^>]*>", "", frag)
            frag = re.sub(r"(?i)</?head[^>]*>", "", frag)
            frag = re.sub(r"(?i)</?body[^>]*>", "", frag)

            fragments.append(f'<div class="label-page">{frag.strip()}</div>')

        if label_page_size == "a4":
            page_css = """
            @page { size: A4; margin: 4mm 10mm 10mm 10mm; }
            .label-page {
                display: inline-block;
                box-sizing: border-box;
                width: 93.5mm;
                height: 140mm;
                max-height: 140mm;
                vertical-align: top;
                margin: 0 3mm 0 0;
                page-break-inside: avoid;
                break-inside: avoid;
                overflow: hidden;
            }
            .label-page:nth-child(even) { margin-right: 0; }
            .label-page:nth-child(4n + 1), .label-page:nth-child(4n + 2) { margin-bottom: 3mm; }
            .label-page:nth-child(4n + 3), .label-page:nth-child(4n + 4) { margin-bottom: 0; }
            .label-page:nth-child(4n) { page-break-after: always; }
            .label-page:last-child { page-break-after: auto; }
            .label-page .label-content {
                height: 100%;
                max-height: 140mm;
                min-height: 0;
                overflow: hidden;
                box-sizing: border-box;
            }
            .label-page .label-content-inner {
                width: 107%;
                transform: scale(0.935);
                transform-origin: top left;
            }
            .label-page .label-content-inner .header { min-height: 22mm; }
            .label-page .label-content-inner .block:first-of-type {
                padding-top: 1.5mm;
                padding-bottom: 2mm;
            }
            html, body { margin: 0; padding: 0; background: white; }
            body { font-family: Arial, Helvetica, sans-serif; font-size: 8px; }
            img { max-width: 100%; height: auto; display: block; }
            """
        elif label_page_size == "a4_single":
            page_css = """
            @page { size: A4; margin: 10mm; }
            .label-page {
                width: 190mm;
                min-height: 277mm;
                margin: 0;
                padding: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                page-break-after: always;
                page-break-inside: avoid;
                box-sizing: border-box;
            }
            .label-page:last-child { page-break-after: auto; }
            .label-page .label-content {
                width: 190mm;
                height: 277mm;
                min-height: 277mm;
                max-height: 277mm;
                box-sizing: border-box;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .label-page .label-content-inner {
                width: 100mm;
                min-height: 150mm;
                transform: scale(1.847);
                transform-origin: center center;
                flex-shrink: 0;
            }
            html, body { margin: 0; padding: 0; background: white; }
            body { font-family: Arial, Helvetica, sans-serif; font-size: 8px; width: 190mm; }
            img { max-width: 100%; height: auto; display: block; }
            """
        elif label_page_size == "3x5":
            page_css = """
            @page { size: 3in 5in; margin: 0; }
            .label-page {
                width: 3in;
                height: 5in;
                page-break-after: always;
                overflow: hidden;
            }
            .label-page:last-child { page-break-after: auto; }
            html, body { margin: 0; padding: 0; background: white; }
            body { font-family: Arial, Helvetica, sans-serif; font-size: 8px; }
            img { max-width: 100%; height: auto; display: block; }
            """
        else:
            page_css = """
            @page { size: 4in 6in; margin: 0; }
            .label-page {
                width: 4in;
                height: 6in;
                page-break-after: always;
                overflow: hidden;
            }
            .label-page:last-child { page-break-after: auto; }
            html, body { margin: 0; padding: 0; background: white; }
            body { font-family: Arial, Helvetica, sans-serif; font-size: 8px; }
            img { max-width: 100%; height: auto; display: block; }
            """

        combined_css = (first_css + page_css) if first_css else page_css

        combined_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{combined_css}</style>
</head>
<body>
{''.join(fragments)}
</body>
</html>
"""

        label_pdf = HTML(
            string=combined_html, base_url=request.build_absolute_uri("/")
        ).write_pdf(
            font_config=font_config,
            optimize_size=("images", "fonts"),
            presentational_hints=True,
        )

        pdfs = []
        if ats_pdf_list:
            pdfs.extend(ats_pdf_list)
        pdfs.append(label_pdf)

        final_pdf = merge_pdfs(pdfs)

        response = HttpResponse(final_pdf, content_type="application/pdf")
        filename = f"labels_{timestamp}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(final_pdf)
        return response

    except Exception as e:
        logger.error(f"Bulk label PDF error: {e}", exc_info=True)
        messages.error(request, "Failed to generate labels.")
        return redirect("user_panel:dashboard")


@user_required
def download_invoice(request):
    """
    Single invoice => return single PDF.
    Multiple invoices => return a single merged PDF (one invoice per page).
    """
    if request.method != "GET":
        messages.error(request, "Invalid request method.")
        return redirect("user_panel:dashboard")

    raw_ids = request.GET.get("order_id", "")
    if not raw_ids:
        messages.error(request, "At least one order must be selected.")
        return redirect("user_panel:dashboard")

    order_ids = [int(pid) for pid in raw_ids.split(",") if pid.strip().isdigit()]
    if not order_ids:
        messages.error(request, "No valid order IDs provided.")
        return redirect("user_panel:dashboard")

    MAX_LIMIT = getattr(settings, "MAX_ORDER_DOWNLOAD_LIMIT", 50)
    if len(order_ids) > MAX_LIMIT:
        messages.error(request, f"You can download up to {MAX_LIMIT} invoices at once.")
        return redirect("user_panel:dashboard")

    # Fetch orders that belong to this user
    orders = (
        Order.objects.filter(id__in=order_ids, user=request.user)
        .select_related(
            "shipping_address", "shipment", "payment", "hub", "user__label_setting"
        )
        .prefetch_related("items", "items__product")
    )
    valid_ids = set(orders.values_list("id", flat=True))
    if not valid_ids:
        messages.error(request, "No matching orders found.")
        return redirect("user_panel:dashboard")

    missing = set(order_ids) - valid_ids
    if missing:
        messages.warning(request, f"Invoices skipped: {', '.join(map(str, missing))}.")

    font_config = FontConfiguration()
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    template_name = "user_panel/invoice/download.dj"  # your invoice fragment template

    # Single invoice -> return PDF directly
    if orders.count() == 1:
        order = orders.first()
        html_fragment = render_to_string(
            template_name,
            {
                "order": order,
                "STATIC_URL": settings.STATIC_URL,
                "MEDIA_URL": settings.MEDIA_URL,
                "request": request,
            },
        )
        try:
            pdf_bytes = HTML(
                string=html_fragment, base_url=request.build_absolute_uri("/")
            ).write_pdf(
                font_config=font_config,
                optimize_size=("images", "fonts"),
                presentational_hints=True,
            )
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            filename = f"invoice_{order.order_number}_{timestamp}.pdf".replace("/", "_")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = len(pdf_bytes)
            return response
        except Exception as e:
            logger.error(f"Single invoice PDF error: {e}", exc_info=True)
            messages.error(
                request, "Failed to generate the invoice. Please try again later."
            )
            return redirect("user_panel:dashboard")

    # Multiple orders -> single merged PDF (one invoice per page)
    try:
        invoice_fragments = []
        first_css = None

        for i, order in enumerate(orders):
            frag = render_to_string(
                template_name,
                {
                    "order": order,
                    "STATIC_URL": settings.STATIC_URL,
                    "MEDIA_URL": settings.MEDIA_URL,
                    "request": request,
                },
            )

            # Extract first <style>...</style> block (if present) to include only once
            if i == 0:
                m = re.search(r"(?s)<style[^>]*>(.*?)</style>", frag)
                if m:
                    first_css = m.group(1).strip()

            # Remove all style blocks from the fragment to avoid duplication
            frag_clean = re.sub(r"(?s)<style[^>]*>.*?</style>", "", frag)

            # Optionally remove outer html/body tags if your fragment includes them (not expected here)
            frag_clean = re.sub(r"(?i)</?html[^>]*>", "", frag_clean)
            frag_clean = re.sub(r"(?i)</?body[^>]*>", "", frag_clean)

            invoice_fragments.append(frag_clean)

        # Ensure we have some CSS; if not, provide minimal page-break CSS plus A4 page settings
        page_css = """
        @page { size: A4 portrait; margin: 16mm; }
        .invoice-page { page-break-after: always; break-after: page; }
        .invoice-page:last-child { page-break-after: auto; break-after: auto; }
        """
        combined_css = (first_css + "\n" + page_css) if first_css else page_css

        # Build combined HTML with each fragment wrapped to force page breaks
        combined_html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      {combined_css}
    </style>
  </head>
  <body>
    {"".join(f'<div class="invoice-page">{frag}</div>' for frag in invoice_fragments)}
  </body>
</html>
"""

        pdf_bytes = HTML(
            string=combined_html, base_url=request.build_absolute_uri("/")
        ).write_pdf(
            font_config=font_config,
            optimize_size=("images", "fonts"),
            presentational_hints=True,
        )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f"invoices_{timestamp}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(pdf_bytes)
        return response

    except Exception as e:
        logger.error(f"Bulk invoice (merged) generation error: {e}", exc_info=True)
        messages.error(request, "Failed to generate invoices. Please try again later.")
        return redirect("user_panel:dashboard")


@user_required
def get_awb_details(request):
    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    awb_number = request.GET.get("awb_number", "").strip()

    if not awb_number:
        return JsonResponse({"error": "AWB number is required"}, status=400)

    order = (
        Order.objects.filter(awb_number=awb_number, user=request.user)
        .select_related("shipment", "shipping_address")
        .first()
    )

    if not order:
        return JsonResponse(
            {"error": "No order found for the provided AWB number"}, status=404
        )

    shipment = order.shipment
    if shipment is None:
        return JsonResponse({"error": "Shipment data doesn't exists"})

    shipping_address = order.shipping_address
    order_items = order.items.all()
    products = []
    for item in order_items:
        products.append(
            {
                "name": item.product.name,
                "sku": item.product.sku,
                "qty": item.quantity,
                "price": item.product.price,
                "hsn_code": "",
                "invoice_no": "",
                "category": "",
            }
        )

    data = {
        # Shipping Information
        "customer_name": shipping_address.name,
        "company_name": shipping_address.company_name,
        "mobile_no": shipping_address.phone,
        "alt_mobile_no": shipping_address.alt_phone,
        "email": shipping_address.email,
        "address_line1": shipping_address.line1,
        "address_line2": shipping_address.line2,
        "landmark": shipping_address.landmark,
        "pincode": shipping_address.pin_code,
        "city": shipping_address.city,
        "state": shipping_address.state,
        "country": shipping_address.country,
        # Order Information
        "order_id": order.order_number,
        "products": products,
        "weight_in_kg": shipment.package_weight_kg,
        "package_length_cm": shipment.package_length_cm,
        "package_width_cm": shipment.package_width_cm,
        "package_height_cm": shipment.package_height_cm,
    }

    return JsonResponse(data)


@user_required
def shopify_integration(request):
    ctx = {"stores": ShopifyStore.get_stores_dashboard_data(request.user)}
    return render(request, "user_panel/integration/shopify.dj", ctx)
