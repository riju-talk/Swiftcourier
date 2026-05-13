from datetime import datetime, timedelta
from django.shortcuts import redirect
from account.models import Courier
from order_manager.models import Hub, Order, Payment
from django.contrib import messages
from django.db.models import Q, QuerySet
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage, Page


def filter_orders(
    request, data, status: str, order_queryset: QuerySet[Order] = None
) -> tuple[QuerySet[Order]|None, Page|None, int|None, bool]:
    if status not in Order.ALL_ORDER_STATUS and status != "all_orders":
        messages.info(request, "Invalid status")
        return None, None, None, True

    if order_queryset is None:
        order_queryset = Order.objects.all()

    # Base queryset with ordering
    if status == "all_orders":
        order_queryset = order_queryset.filter(user=request.user)
    else:
        order_queryset = order_queryset.filter(status__startswith=status, user=request.user)

    # Filter: Order ID (search in both ID and AWB number)
    order_id = data.get("order_id")
    if order_id:
        try:
            if order_id.startswith("IS"):
                order_id = order_id.replace("IS", "")
            # Try exact ID match first
            order_queryset = order_queryset.filter(
                Q(id=int(order_id)) | Q(order_number__iexact=order_id) | Q(awb_number__iexact=order_id)
            )
        except (ValueError, TypeError):
            # Fallback to AWB number partial match
            pass

    # Filter: Order ID (search in both ID and AWB number)
    courier_partner = data.get("courier_partner")
    if courier_partner:
        try:
            # Try exact ID match first
            order_queryset = order_queryset.filter(
                logistic_partner__id=courier_partner
            )
        except (ValueError, TypeError):
            # Fallback to AWB number partial match
            pass

    # Filter: Exact AWB number match
    awb_number = data.get("awb_number")
    if awb_number:
        order_queryset = order_queryset.filter(awb_number__iexact=awb_number)

    # Filter: Order type (payment method)
    payment_method = data.get("payment_method")
    if payment_method:
        if payment_method in Payment.ALL_PAYMENT_METHODS:
            order_queryset = order_queryset.filter(payment__method=payment_method)
        else:
            messages.error(request, f"Invalid payment method: {payment_method}")

    # Filter: Multiple warehouses
    warehouse_id = data.get("warehouse")
    if warehouse_id:
        valid_hubs = Hub.objects.filter(id=warehouse_id, user=request.user)
        if valid_hubs.exists():
            order_queryset = order_queryset.filter(hub__in=valid_hubs)
        else:
            messages.error(request, "Invalid warehouse selection")

    # Filter: Channel
    channel = data.get("channel")
    if channel:
        order_queryset = order_queryset.filter(channel=channel)

    # Filter: Product name search
    product_name = data.get("product_name")
    if product_name:
        order_queryset = order_queryset.filter(
            items__product__name__icontains=product_name
        ).distinct()

    # Universal search filter
    search_query = data.get("q")
    if search_query:
        order_queryset = order_queryset.filter(
            Q(id__icontains=search_query)  # Partial match for ID
            | Q(awb_number__icontains=search_query)
            | Q(order_number__icontains=search_query)
            | Q(items__product__name__icontains=search_query)
            
            | Q(shipping_address__name__icontains=search_query)
            | Q(shipping_address__phone__icontains=search_query)
            | Q(shipping_address__alt_phone__icontains=search_query)
            | Q(shipping_address__company_name__icontains=search_query)
            
            | Q(billing_address__phone__icontains=search_query)
            | Q(billing_address__alt_phone__icontains=search_query)
            | Q(billing_address__company_name__icontains=search_query)
        )
        if search_query.startswith("IS"):
            order_queryset = order_queryset.filter(
                id__icontains=search_query.replace("IS", "")
            )

        order_queryset = order_queryset.distinct()

    # Filter: Date Range ("Jun 02, 2025 - Jun 08, 2025")
    date_range = data.get("dateRange")
    if date_range:
        try:
            # Expect format "Mon DD, YYYY - Mon DD, YYYY"
            parts = [p.strip() for p in date_range.split("-")]
            if len(parts) == 2:
                start = datetime.strptime(parts[0], "%b %d, %Y")
                # include entire end day
                end = datetime.strptime(parts[1], "%b %d, %Y") + timedelta(
                    hours=23, minutes=59, seconds=59
                )
                # Validate order of dates
                if end < start:
                    messages.error(request, "End date cannot be before start date.")
                else:
                    if status in ["ready_to_ship", "cancelled"]:
                        order_queryset = order_queryset.filter(
                            created_at__range=(start, end)
                        )
                    else:
                        try:
                            order_queryset = order_queryset.filter(
                                shipment__booked_at__range=(start, end)
                            )
                        except:
                            order_queryset = order_queryset.filter(
                                created_at__range=(start, end)
                            )
            else:
                raise ValueError("Incorrect format")
        except ValueError:
            messages.error(
                request, "Invalid date range format. Use 'Mon DD, YYYY - Mon DD, YYYY'."
            )

    # Pagination setup
    page_size = data.get("page_size", 50)
    try:
        page_size = int(page_size)
        if page_size not in {10, 50, 100, 200, 500}:
            page_size = 50
            messages.info(request, f"Page size changed to {page_size}")
    except (ValueError, TypeError):
        page_size = 50

    # Date Range Filter
    date_range = request.GET.get("date_range")
    if date_range and "_" in date_range:
        try:
            start_str, end_str = date_range.split("_")
            start_date = datetime.strptime(start_str, "%d-%m-%Y")
            end_date = datetime.strptime(end_str, "%d-%m-%Y").replace(
                hour=23, minute=59, second=59
            )
            order_queryset = order_queryset.filter(
                created_at__range=(start_date, end_date)
            )
        except ValueError:
            messages.error(request, "Invalid date range format")

    paginator = Paginator(order_queryset, page_size)
    page_number = data.get("page", 1)

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return order_queryset, page_obj, page_size, False
