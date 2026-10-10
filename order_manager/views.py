# Standard library imports
import base64
import hashlib
import hmac
import io
import json
import logging
import uuid
import re
from celery import group
import pandas as pd


# Django imports
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.utils import timezone
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.views.decorators.csrf import csrf_exempt

from collections import defaultdict
from utils.lazy_weasyprint import HTML, FontConfiguration

# Third-party imports
from .tasks import (
    ship_orders_by_preference,
    ship_orders,
    bulk_cancel_orders,
)
from wallet.models import Transaction

# Local app imports
from account.decorators import user_required
from account.models import Courier, CourierPreferenceSequence, RateCard
from .models import (
    Address,
    BulkOrderFile,
    Hub,
    Order,
    OrderItem,
    Payment,
    Product,
    Shipment,
)

from .validation import STATUS_MAPPING, validate_and_process_bulk_orders
from utils.get_courier_handler import get_courier_handler


logger = logging.getLogger("my-logger")
User = get_user_model()


@user_required
@transaction.atomic
def edit_order(request):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("user_panel:shipment", "pending_pickup")

    data = request.POST

    # ------------------------------------------------
    # Fetch Order
    # ------------------------------------------------
    order = (
        Order.objects.select_related("shipping_address", "payment", "shipment")
        .prefetch_related("items__product")
        .filter(user=request.user, id=data.get("real_order_id"))
        .first()
    )

    if not order or order.status not in ["ready_to_ship", "cancelled"]:
        messages.error(request, "Order cannot be edited.")
        return redirect("user_panel:shipment", "pending_pickup")

    # ------------------------------------------------
    # Helper functions
    # ------------------------------------------------
    def clean_str(val):
        return (val or "").strip()

    def clean_float(val, default=0.0):
        try:
            return float(val)
        except:
            return default

    def clean_int(val, default=0):
        try:
            return int(val)
        except:
            return default

    def hsn_for_suffix(suffix):
        key_suffix = suffix if suffix else ""
        idx = suffix if suffix else "1"
        return clean_str(
            data.get(f"hsn_code{key_suffix}") or data.get(f"product_hsn_{idx}")
        )

    # ------------------------------------------------
    # Update order number
    # ------------------------------------------------
    if val := data.get("order_id"):
        order.order_number = clean_str(val)

    # ------------------------------------------------
    # Parse Product Data (YOUR PAYLOAD FORMAT)
    # ------------------------------------------------
    product_data = {}

    for key in data.keys():
        match = re.match(r"product_name(\d*)$", key)
        if not match:
            continue

        suffix = match.group(1)  # "" OR "3" OR "4"

        product_data[suffix] = {
            "pid": data.get(f"product_id{suffix}"),
            "name": clean_str(data.get(f"product_name{suffix}")),
            "qty": clean_int(data.get(f"quantity{suffix}")),
            "price": clean_float(data.get(f"total_price{suffix}")),
            "sku": clean_str(data.get(f"sku_code{suffix}")),
            "hsn_code": hsn_for_suffix(suffix),
        }

    logger.debug(
        f"Product data: {product_data} for order {order.id} by user {request.user.id}"
    )
    # ------------------------------------------------
    # Update / Create Order Items
    # ------------------------------------------------
    existing_items = {
        item.product_id: item for item in order.items.select_related("product")
    }
    incoming_product_ids = set()

    for pdata in product_data.values():
        pid = pdata["pid"]
        qty = pdata["qty"]
        price = pdata["price"]

        if qty <= 0:
            continue

        # ----------------------------
        # EXISTING PRODUCT
        # ----------------------------
        if pid:
            pid = clean_int(pid)
            incoming_product_ids.add(pid)

            order_item = existing_items.get(pid)

            if order_item:
                product = order_item.product

                product.name = pdata["name"]
                product.price = price
                product.sku = pdata["sku"]
                product.hsn_code = pdata["hsn_code"]
                product.save()

                order_item.quantity = qty
                order_item.total_price = price
                order_item.unit_price = price / qty if qty > 0 else 0
                order_item.sku_code = pdata["sku"]
                order_item.save()
                logger.debug(
                    f"Updated OrderItem {order_item.id} for product {product.id} in order {order.id}"
                )
        # ----------------------------
        # NEW PRODUCT
        # ----------------------------
        else:
            product = Product.objects.create(
                name=pdata["name"],
                price=price,
                sku=pdata["sku"],
                hsn_code=pdata["hsn_code"],
                weight_kg=clean_float(data.get("weight"), default=0.5),
                length_cm=clean_int(data.get("length"), default=10),
                width_cm=clean_int(data.get("breadth"), default=10),
                height_cm=clean_int(data.get("height"), default=10),
            )

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=qty,
                unit_price=price / qty if qty > 0 else 0,
                total_price=price,
                sku_code=pdata["sku"],
            )
            incoming_product_ids.add(product.id)
            logger.debug(
                f"Created new Product {product.id} and OrderItem for order {order.id}"
            )

    # ------------------------------------------------
    # Delete Removed Products
    # ------------------------------------------------
    order.items.exclude(product_id__in=incoming_product_ids).delete()
    logger.debug(
        f"Deleted OrderItems for products not in incoming data for order {order.id}"
    )

    # ------------------------------------------------
    # Update Shipping Address
    # ------------------------------------------------
    address_map = {
        "name": "consignee_name",
        "phone": "consignee_phone",
        "alt_phone": "consignee_alt_phone",
        "email": "consignee_email",
        "line1": "address",
        "line2": "address2",
        "landmark": "landmark",
        "company_name": "company_name",
        "pin_code": "pin_code",
        "city": "city",
        "state": "state",
        "country": "country",
    }

    addr = order.shipping_address
    for attr, field in address_map.items():
        if field in data:
            setattr(addr, attr, clean_str(data.get(field)))
    addr.save()

    # ------------------------------------------------
    # Update Payment
    # ------------------------------------------------
    payment_map = {
        "method": "payment_method",
        # shippping charges 0
        # "shipping_charges": "shipping_charges",
        "cod_charges": "cod_charges",
        "discount": "discounts",
        "gift_wrap_charges": "gift_wrap",
        "other_charges": "other_charges",
        "tax_percent": "tax_percent",
    }
    payment = order.payment
    for attr, field in payment_map.items():
        if field not in data:
            continue
        if attr == "method":
            setattr(payment, attr, data.get(field))
        else:
            setattr(payment, attr, clean_float(data.get(field)))
    payment.save()

    # ------------------------------------------------
    # Update Shipment
    # ------------------------------------------------
    shipment_map = {
        "package_weight_kg": "weight",
        "package_length_cm": "length",
        "package_width_cm": "breadth",
        "package_height_cm": "height",
    }
    shipment = order.shipment
    for attr, field in shipment_map.items():
        if field in data:
            setattr(shipment, attr, clean_float(data.get(field)))
    shipment.save()

    # ------------------------------------------------
    # Recalculate totals
    # ------------------------------------------------
    order.save()
    order.refresh_from_db()
    order.calculate_total()

    manual_invoice_raw = data.get("invoice_value")
    manual_total_raw = data.get("total_value")
    update_fields = []
    if manual_invoice_raw not in [None, ""]:
        order.invoice_amount = clean_float(manual_invoice_raw)
        update_fields.append("invoice_amount")
    if manual_total_raw not in [None, ""]:
        order.total_amount = clean_float(manual_total_raw)
        update_fields.append("total_amount")
    if update_fields:
        order.save(update_fields=update_fields)

    payment.amount = order.total_amount
    payment.cod_collectable_amount = (
        order.total_amount if payment.method == "cod" else 0
    )
    payment.save(update_fields=["amount", "cod_collectable_amount"])

    messages.success(request, "Order updated successfully.")
    return redirect("user_panel:shipment", "ready_to_ship")


@user_required
@csrf_exempt
def save_single_order(request):
    if request.method != "POST":
        return redirect("index")

    data = request.POST
    errors = []

    if data.get("myAction") == "edit":
        return edit_order(request)

    # 1) Required‐field validation
    required_fields = {
        "consignee_name": "Consignee name is required",
        "consignee_phone": "Phone number is required",
        "address": "Address is required",
        "pin_code": "PIN code is required",
        "city": "City is required",
        "state": "State is required",
        "country": "Country is required",
        "payment_method": "Payment method is required",
        "weight": "Package weight is required",
        "length": "Package length is required",
        "breadth": "Package breadth is required",
        "height": "Package height is required",
        "order_id": "Order Id is required",
    }

    for field, msg in required_fields.items():
        if not data.get(field):
            errors.append(msg)

    # 2) Line items validation
    product_name = data.get("product_name", [])
    quantities = data.get("quantity", [])
    total_price = data.get("total_price", [])

    # Prices per unit (if wanted) or derive from Product.price
    # Here we just trust the product.price
    if not all([product_name, quantities, total_price]):
        errors.append("Product, quantity, and total price are required")
    else:
        if not quantities.isdigit() or int(quantities) < 1:
            print(f"Invalid quantity: {quantities}")
            errors.append("Each quantity must be a positive integer")

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect("user_panel:add-order")

    product_data = [
        # [product_name, quantities, total_price, sku_code]  this is basic structure
    ]
    for i in data:
        if i.startswith("product_name"):
            no = i.replace("product_name", "")
            idx = no if no else "1"
            product_data.append(
                [
                    data.get(f"product_name{no}"),
                    data.get(f"quantity{no}"),
                    data.get(f"total_price{no}"),
                    data.get(f"sku_code{no}"),
                    (
                        data.get(f"hsn_code{no}")
                        or data.get(f"product_hsn_{idx}")
                        or ""
                    ).strip(),
                ]
            )

    try:

        def clean_phone(phone):
            if not phone:
                return ""
            phone = phone.strip().replace(" ", "").replace("-", "")
            if phone.startswith("+91"):
                phone = phone[3:]
            if phone.startswith("91") and len(phone) > 10:
                phone = phone[2:]
            return phone[:10]  # keep last 10 digits

        with transaction.atomic():
            # 3) Create shipping address
            address = Address.objects.create(
                user=request.user,
                line1=data.get("address", ""),
                line2=data.get("address2", ""),
                landmark=data.get("landmark", ""),
                company_name=data.get("company_name", ""),
                city=data.get("city", ""),
                state=data.get("state", ""),
                pin_code=data.get("pin_code", ""),
                country=data.get("country", ""),
                phone=clean_phone(data.get("consignee_phone", "")),
                name=data.get("consignee_name", ""),
                alt_phone=clean_phone(data.get("consignee_alt_phone", "")),
                email=data.get("consignee_email", ""),
            )

            # 4) Create the Order (total_amount will be updated)
            order = Order.objects.create(
                user=request.user,
                shipping_address=address,
                billing_address=address,  # set if present
                channel=data.get("channel", ""),
                order_number=data.get("order_id", ""),
                total_amount=0,
                invoice_amount=0,
            )

            # 5) Create OrderItems, using the real Product FK
            for prod_name, qty_str, total_str, sku, hsn_code in product_data:
                qty = int(qty_str)

                product = Product.objects.create(
                    name=prod_name,
                    sku=sku,
                    hsn_code=hsn_code,
                    price=float(total_str) / qty,
                    weight_kg=float(data.get("weight")) if data.get("weight") else 0,
                    length_cm=float(data.get("length")) if data.get("length") else 0,
                    width_cm=float(data.get("breadth")) if data.get("breadth") else 0,
                    height_cm=float(data.get("height")) if data.get("height") else 0,
                )

                # unit_price from product.price
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=product.price,
                    total_price=product.price * qty,
                    sku_code=product.sku,
                )

            # 6) Recalculate order.total_amount
            order.calculate_total()

            # 7) Create Payment with updated total_amount
            def to_float(value, default=0.0):
                try:
                    return float(value) if value not in [None, ""] else default
                except (ValueError, TypeError):
                    return default

            manual_invoice = to_float(data.get("invoice_value"), None)
            manual_total = to_float(data.get("total_value"), None)
            update_fields = []
            if manual_invoice is not None:
                order.invoice_amount = manual_invoice
                update_fields.append("invoice_amount")
            if manual_total is not None:
                order.total_amount = manual_total
                update_fields.append("total_amount")
            if update_fields:
                order.save(update_fields=update_fields)

            _ = Payment.objects.create(
                order=order,
                method=data["payment_method"],
                status="pending",
                transaction_id="",
                amount=order.total_amount,
                # shipping charges 0
                # shipping_charges=to_float(data.get("shipping_charges")),
                cod_charges=to_float(data.get("cod_charges")),
                cod_collectable_amount=(
                    order.total_amount if data["payment_method"] == "cod" else 0.0
                ),
                discount=to_float(data.get("discounts")),
                gift_wrap_charges=to_float(data.get("gift_wrap")),
                other_charges=to_float(data.get("other_charges")),
                tax_percent=to_float(data.get("tax_percent")),
            )

            # 8) Create Shipment
            _ = Shipment.objects.create(
                order=order,
                package_weight_kg=float(data["weight"]) if data.get("weight") else 0,
                package_length_cm=float(data["length"]) if data.get("length") else 0,
                package_width_cm=float(data["breadth"]) if data.get("breadth") else 0,
                package_height_cm=float(data["height"]) if data.get("height") else 0,
            )

            messages.success(request, "Order saved successfully")
            return redirect("user_panel:shipment", "ready_to_ship")

            # return redirect(reverse("user_panel:add-order") + "?submitted=true")

    except Exception as e:
        logger.exception("Failed to saave single order: ")
        messages.error(request, f"Could not save order: {e}")
        return redirect("user_panel:add-order")


@user_required
def save_bulk_order(request):
    def redirect_to_bulk_page(**params):
        query = {"active_tab": "bulk", **params}
        return redirect(f"{reverse('user_panel:add-order')}?{urlencode(query)}")

    def store_failed_rows_download(
        failed_rows: list[dict], original_headers: list[str], uploaded_filename: str
    ) -> str | None:
        if not failed_rows:
            return None

        download_key = uuid.uuid4().hex
        file_type = "csv" if uploaded_filename.lower().endswith(".csv") else "xlsx"
        session_downloads = request.session.get("bulk_failed_downloads", {})
        session_downloads[download_key] = {
            "headers": original_headers,
            "rows": failed_rows,
            "file_type": file_type,
        }
        request.session["bulk_failed_downloads"] = session_downloads
        request.session.modified = True
        return download_key

    if request.method != "POST":
        messages.error(request, "Invalid request method")
        return redirect_to_bulk_page()

    bulk_file = request.FILES.get("bulk_order_file")

    if not bulk_file:
        messages.error(request, "Bulk Order File Required")
        return redirect_to_bulk_page()

    try:
        orders_data, validation_errors, original_headers, failed_rows = (
            validate_and_process_bulk_orders(bulk_file, request.user)
        )
        total_uploads = len(orders_data) + len(failed_rows)

        if validation_errors and not orders_data:
            download_key = store_failed_rows_download(
                failed_rows, original_headers, bulk_file.name
            )
            messages.error(
                request,
                "The uploaded file contains invalid orders. Review the summary on this page and download the failed orders file for row-level error details.",
            )
            return redirect_to_bulk_page(
                bulk_completed=1,
                bulk_total=total_uploads,
                bulk_success=0,
                bulk_failed=len(failed_rows),
                bulk_download_key=download_key or "",
            )

        if not orders_data:
            messages.error(request, "No valid orders found in the file")
            return redirect_to_bulk_page(
                bulk_completed=1, bulk_total=0, bulk_success=0, bulk_failed=0
            )

        bulk_order_file = BulkOrderFile.objects.create(file=bulk_file)

        success_count = 0
        failed_count = len(failed_rows)
        errors = list(validation_errors)

        for order_data in orders_data:
            try:
                with transaction.atomic():
                    # Create Address with .get() and defaults
                    address = Address.objects.create(
                        user=request.user,
                        name=f"{order_data.get('first_name') or ''} {order_data.get('last_name') or ''}".strip(),
                        line1=order_data.get("address_1") or "",
                        line2=order_data.get("address_2") or "",
                        landmark=order_data.get("landmark") or "",
                        city=order_data.get("city") or "",
                        state=order_data.get("state") or "",
                        pin_code=(order_data.get("pincode") or ""),
                        country=order_data.get("country") or "India",
                        phone=str(order_data.get("mobile") or "")[:10],
                        alt_phone=str(order_data.get("alternate_phone") or "")[:10],
                        email=order_data.get("email") or "",
                        company_name=order_data.get("company_name") or "",
                    )

                    order_date = order_data.get("order_date")
                    # Create Order with .get() for optional fields
                    order = Order.objects.create(
                        user=request.user,
                        order_date=order_date,
                        order_number=str(order_data.get("order_id") or ""),
                        shipping_address=address,
                        billing_address=address,
                        channel="bulk_upload",
                        status=STATUS_MAPPING.get(
                            (order_data.get("status") or "").lower(), "ready_to_ship"
                        ),
                        total_amount=0,
                        bulk_order_file=bulk_order_file,
                    )

                    # Create Products and OrderItems
                    total_amount = 0
                    for product in order_data.get("products") or []:
                        # Ensure required product fields exist
                        sku = product.get("sku") or 0
                        name = product.get("name") or 0
                        price = product.get("price") or 0
                        quantity = product.get("quantity") or 0
                        total = product.get("total") or 0

                        if not all([name, price, quantity, total]):
                            errors.append(
                                f"Order {order_data.get('order_id') or ''}: Missing product fields"
                            )
                            raise ValueError("Missing product fields")

                        product_obj = Product.objects.create(
                            sku=sku,
                            name=name,
                            price=float(price),
                            weight_kg=float(order_data.get("weight") or 0.0),
                            length_cm=int(float(order_data.get("length") or 0)),
                            width_cm=int(float(order_data.get("breadth") or 0)),
                            height_cm=int(float(order_data.get("height") or 0)),
                        )

                        OrderItem.objects.create(
                            order=order,
                            product=product_obj,
                            quantity=int(quantity),
                            unit_price=float(price),
                            total_price=float(total),
                            sku_code=sku,
                        )
                        total_amount += float(total)

                    order.total_amount = total_amount
                    order.save()

                    # Create Payment with .get() for charges
                    Payment.objects.create(
                        order=order,
                        method=order_data.get("payment_type") or "prepaid",
                        status="pending",
                        amount=order.total_amount,
                        # shipping charges 0
                        # shipping_charges=float(
                        #     order_data.get("shipping_charges") or 0.0
                        # ),
                        cod_charges=float(order_data.get("cod_charges") or 0.0),
                        cod_collectable_amount=float(
                            order.total_amount
                            or order_data.get("cod_collectable_amount")
                            or order.total_amount
                        ),
                        discount=float(order_data.get("discount") or 0.0),
                    )

                    # Create Shipment with .get() for dimensions
                    Shipment.objects.create(
                        order=order,
                        package_weight_kg=float(order_data.get("weight") or 0.0),
                        package_length_cm=int(float(order_data.get("length") or 0)),
                        package_width_cm=int(float(order_data.get("breadth") or 0)),
                        package_height_cm=int(float(order_data.get("height") or 0)),
                        hub=order.hub,
                    )

                    success_count += 1

            except Exception as e:
                error_message = f"Order {order_data.get('order_id', '')}: {str(e)}"
                logger.error(
                    f"Error saving order {order_data.get('order_id', '')}: {str(e)}\nDATA: {orders_data}"
                )
                failed_count += 1
                errors.append(error_message)
                failed_rows.append(
                    {
                        "row_number": order_data.get("_row_number"),
                        "row_data": order_data.get("_source_row", {}),
                        "reason": error_message,
                        "reasons": [error_message],
                    }
                )

        # Prepare result message
        result_msg = []
        if success_count:
            result_msg.append(f"Successfully processed {success_count} orders")
        if failed_count:
            result_msg.append(f"Failed to process {failed_count} orders")
        if errors:
            messages.error(
                request,
                "Some orders in the uploaded file could not be processed. Use the failed orders download for the exact validation or processing errors.",
            )

        if result_msg:
            messages.info(request, " | ".join(result_msg))

    except Exception as e:
        logger.error(f"Bulk order error: {str(e)}")
        messages.error(request, f"Error processing bulk orders: {str(e)}")
        return redirect_to_bulk_page()

    download_key = store_failed_rows_download(
        failed_rows, original_headers, bulk_file.name
    )
    return redirect_to_bulk_page(
        bulk_completed=1,
        bulk_total=success_count + failed_count,
        bulk_success=success_count,
        bulk_failed=failed_count,
        bulk_download_key=download_key or "",
    )


@user_required
def download_failed_bulk_orders(request, download_key: str):
    def format_failed_reason_for_export(failed_row: dict) -> str:
        reasons = failed_row.get("reasons")
        if not reasons:
            reasons = [failed_row.get("reason", "")]

        cleaned_reasons = []
        for reason in reasons:
            cleaned = re.sub(r"^Row\s+\d+:\s*", "", reason or "").strip()
            if cleaned:
                cleaned_reasons.append(cleaned)

        if not cleaned_reasons:
            return ""
        if len(cleaned_reasons) == 1:
            return cleaned_reasons[0]
        return "\n".join(
            f"{index}. {reason}"
            for index, reason in enumerate(cleaned_reasons, start=1)
        )

    bulk_failed_downloads = request.session.get("bulk_failed_downloads", {})
    download_payload = bulk_failed_downloads.get(download_key)

    if not download_payload:
        messages.error(request, "Failed-order download file not found.")
        return redirect(
            f"{reverse('user_panel:add-order')}?{urlencode({'active_tab': 'bulk'})}"
        )

    original_headers = download_payload.get("headers", [])
    failed_rows = download_payload.get("rows", [])
    file_type = download_payload.get("file_type", "csv")

    export_rows = []
    for failed_row in failed_rows:
        row_data = failed_row.get("row_data", {})
        row_export = {header: row_data.get(header, "") for header in original_headers}
        row_export["Failure Reason"] = format_failed_reason_for_export(failed_row)
        export_rows.append(row_export)

    columns = [*original_headers, "Failure Reason"]
    df = pd.DataFrame(export_rows, columns=columns)

    if file_type == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="failed_bulk_orders.csv"'
        )
        df.to_csv(response, index=False)
        return response

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Failed Orders")

    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = 'attachment; filename="failed_bulk_orders.xlsx"'
    return response


@user_required
def ship_order(request):
    data = request.POST

    _order_ids = data.get("order_ids", "").split(",")
    order_ids = [oid for oid in _order_ids if oid.isdigit()]

    hub_id = data.get("warehouse")
    if hub_id is None:
        messages.info(request, "Please select a warehouse.")
        return redirect("user_panel:shipment", "ready_to_ship")

    hub = Hub.objects.filter(id=hub_id, user=request.user).first()
    if hub is None:
        messages.info(request, "Please select a valid warehouse.")
        return redirect("user_panel:shipment", "ready_to_ship")

    courier_id = data.get("courier")
    if courier_id == "preference":
        messages.info(request, "Courier Preference is Disabled Right Now!")
        return redirect("user_panel:shipment", "ready_to_ship")
        cp = CourierPreferenceSequence.get_user_preference(request.user)
        if not cp:
            messages.info(
                request,
                "No courier preferences found. Please set your courier preferences first.",
            )
            return redirect("user_panel:shipment", "ready_to_ship")

        _ = ship_orders_by_preference.enqueue(
            order_ids=order_ids,
            hub_id=hub.id,
            user_id=request.user.id,
            auto_fetch_courier_preference=True,
        )

        messages.info(
            request,
            "Orders are being processed for shipping based on your courier preferences.",
        )
        return redirect("user_panel:shipment", "pending_pickup")

    courier = Courier.objects.filter(id=courier_id).first()
    if courier is None:
        messages.info(request, "Courier is invalid.")
        return redirect("user_panel:shipment", "ready_to_ship")

    rate_card = RateCard.objects.filter(user=request.user, courier=courier).first()
    if rate_card is None:
        messages.info(request, "You haven't assigned a rate card for this courier.")
        return redirect("user_panel:shipment", "ready_to_ship")

    ready_order_ids, failed_order_ids = Order.send_to_processing(
        order_ids=order_ids, user=request.user
    )
    failed_orders = len(failed_order_ids)
    if failed_orders:
        messages.error(
            request, f"{failed_orders} orders could not be processed for shipping."
        )

    # ── Batch & group ────────────────────────────────────────────────────────
    batches = [ready_order_ids[i : i + 50] for i in range(0, len(ready_order_ids), 50)]

    job = group(
        ship_orders.s(
            order_ids=batch,
            hub_id=hub.id,
            user_id=request.user.id,
            courier_id=courier.id,
            rate_card_id=rate_card.id,
        )
        for batch in batches
    )

    try:
        result = job.apply_async()
        result.save()
    except Exception:
        # broker unreachable (RabbitMQ/Redis down) - don't 500 the merchant and
        # don't leave the orders stranded in `processing`. Roll them straight
        # back to ready_to_ship so they can retry.
        logger.exception("ship_order: could not queue ship batch")
        Order.objects.filter(id__in=ready_order_ids, user=request.user).update(
            status="ready_to_ship", updated_at=timezone.now()
        )
        messages.error(
            request,
            "Shipping is temporarily unavailable - your orders were not shipped "
            "and are back under Ready to Ship. Please try again in a few minutes.",
        )
        return redirect("user_panel:shipment", "ready_to_ship")
    # ─────────────────────────────────────────────────────────────────────────

    messages.info(
        request,
        f"Shipping {len(ready_order_ids)} order(s) in {len(batches)} batch(es). "
        "They are listed under Processing and move to Ready for Pickup once the "
        "carrier confirms (this page refreshes on its own).",
    )

    # Land the user on Processing, not Pending Pickup: the orders are in
    # `processing` right now and only flip to `pending_pickup` after the async
    # ship task gets an AWB back from the carrier. Redirecting to pending_pickup
    # made freshly-shipped orders look like they had vanished.
    return redirect("user_panel:shipment", "processing")


@user_required
def cancel_order(request, order_id):
    next_url = request.GET.get(
        "next", reverse("user_panel:shipment", args=["pending_pickup"])
    )  # default to homepage if not present

    try:
        order = Order.objects.get(id=order_id, user=request.user)
    except Order.DoesNotExist:
        messages.error(request, "Invalid or unauthorized order ID.")
        return redirect(next_url)

    if order.status == "cancelled":
        messages.info(request, f"Order #{order.id} was already cancelled.")
        return redirect(next_url)

    if order.status == "ready_to_ship":
        order.update_status("cancelled")
        messages.success(request, f"Order #{order.id} has been cancelled.")
        return redirect(next_url)

    if order.status == "pending_pickup":
        try:
            res = get_courier_handler(order.logistic_partner).cancel_shipment(
                order.awb_number
            )
            if res.status_code != 200:
                messages.error(
                    request,
                    f"Failed to cancel order #{order.id} with courier: {res.text}",
                )
                return redirect(next_url)
        except AttributeError:
            messages.error(
                request,
                f"Courier handler not found for cancelling order #{order.id}.",
            )
            return redirect(next_url)

        # carrier booking cancelled -> refund the shipping charge (idempotent
        # per-AWB) and put the order back in Ready to Ship so it can be
        # re-shipped or cancelled outright.
        refund = order.refund_shipping()
        order.cancel_data[str(order.awb_number)] = {
            "cancelled_at": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "courier": (
                f"{order.logistic_partner.name} ({order.logistic_partner.abbreviation})"
                if order.logistic_partner
                else "N/A"
            ),
            "refund_amount": (
                float(refund.amount)
                if refund
                else (order.payment.shipping_charges if order.payment else 0)
            ),
        }
        order.update_status("ready_to_ship")
        order.save(update_fields=["cancel_data"])
        messages.success(
            request,
            f"Shipment for order #{order.id} was cancelled with the carrier"
            + (f" and ₹{refund.amount} refunded" if refund else "")
            + ". The order is back under Ready to Ship.",
        )
        return redirect(next_url)

    # in_transit / out_for_delivery / delivered / rto* / etc. - not cancellable
    # from here, and we must not pretend it was.
    messages.error(
        request,
        f"Order #{order.id} is {order.get_status_display()} and can't be "
        "cancelled here. Raise an NDR or contact support.",
    )
    return redirect(next_url)


@user_required
def cancel_bulk_order(request):
    data = request.POST

    order_ids = data.get("order_ids", "").split(",")
    qs = Order.objects.filter(
        id__in=order_ids,
        user=request.user,
    )
    qs.filter(status="ready_to_ship").update(status="cancelled")
    # -------- Pending Pickup Orders -------
    pending_orders = qs.filter(status="pending_pickup")
    pending_orders.update(status="cancelled")
    bulk_cancel_orders.delay(order_ids=order_ids, user_id=request.user.id)
    messages.success(
        request,
        "Your request is being processed in the background. Orders will be cancelled shortly.",
    )

    return redirect("user_panel:shipment", "ready_to_ship")


@user_required
def order_edit_clone(request, order_id: int, action: str):
    if action not in ["clone", "edit"]:
        messages.error(request, "Invalid action")
        return redirect("user_panel:shipment", "pending_pickup")

    order = Order.objects.filter(user=request.user, id=order_id).first()
    if order is None:
        messages.error(request, "Order not found")
        return redirect("user_panel:shipment", "pending_pickup")

    if order.status not in ["ready_to_ship", "cancelled", "pending_pickup"]:
        messages.error(request, "Order status is not valid")
        return redirect("user_panel:shipment", "pending_pickup")

    key_value = {
        "action": action,
        "order_id": order_id,
        "order_number": order.order_number,
        "name": order.shipping_address.name,
        "contact_no": order.shipping_address.phone,
        "alt_contact_no": order.shipping_address.alt_phone,
        "email": order.shipping_address.email,
        "address": order.shipping_address.line1,
        "address2": order.shipping_address.line2,
        "landmark": order.shipping_address.landmark,
        "company": order.shipping_address.company_name,
        "pin_code": order.shipping_address.pin_code,
        "city": order.shipping_address.city,
        "state": order.shipping_address.state,
        "country": order.shipping_address.country,
        "payment_method": order.payment.method,
        "shipping_charges": order.payment.shipping_charges,
        "cod_charges": order.payment.cod_charges,
        "discounts": order.payment.discount,
        "gift_wrap": order.payment.gift_wrap_charges,
        "other_charges": order.payment.other_charges,
        "tax_percent": order.payment.tax_percent,
        "invoice_value": order.invoice_amount or order.total_amount,
        "total_value": order.total_amount,
        "weight": order.shipment.package_weight_kg,
        "length": order.shipment.package_length_cm,
        "breadth": order.shipment.package_width_cm,
        "height": order.shipment.package_height_cm,
    }

    products = OrderItem.objects.filter(order=order)
    if products.count() == 0:
        messages.error(request, "Order has no products")
        return redirect("user_panel:shipment", "pending_pickup")

    first_product = products.first()
    key_value["product_id"] = first_product.product.id
    key_value["product"] = first_product.product.name
    key_value["qty"] = first_product.quantity
    key_value["total_price"] = first_product.total_price
    key_value["sku"] = first_product.sku_code
    key_value["hsn"] = first_product.product.hsn_code

    for index, product in enumerate(products[1:], start=2):
        key_value[f"product_id{index}"] = product.product.id
        key_value[f"product{index}"] = product.product.name
        key_value[f"qty{index}"] = product.quantity
        key_value[f"total_price{index}"] = product.total_price
        key_value[f"sku{index}"] = product.sku_code
        key_value[f"hsn{index}"] = product.product.hsn_code

    return redirect(f"{reverse('user_panel:add-order')}?{urlencode(key_value)}")


@user_required
def download_manifest(request):
    if request.method != "GET":
        messages.error(request, "Invalid request method")
        return JsonResponse({"error": "Invalid request method"}, status=400)

    data = request.GET
    order_ids = data.get("order_id", "").split(",")

    try:
        next_url = data.get("next_url", "/")
        # Tenant isolation: restrict to the requesting merchant's own orders so
        # arbitrary ids in ?order_id= cannot expose another merchant's manifest.
        orders = (
            Order.objects.filter(id__in=order_ids, user=request.user)
            .exclude(logistic_partner__isnull=True)
            .select_related(
                "logistic_partner", "shipping_address", "payment", "shipment", "hub"
            )
            .prefetch_related("items__product")
        )
    except Exception:
        messages.error(request, "Invalid order IDs")
        return redirect(next_url)

    # Group orders by courier
    grouped = defaultdict(list)
    for o in orders:
        courier = o.logistic_partner
        grouped[courier].append(o)

    font_config = FontConfiguration()
    timestamp = timezone.now()

    all_html = ""

    # Build manifest content for each courier
    for idx, (courier, courier_orders) in enumerate(grouped.items()):
        html_fragment = render_to_string(
            "order_manager/manifest/manifest.dj",  # partial template
            {
                "orders": courier_orders,
                "timestamp": timestamp.strftime("%B %d, %Y, %I:%M %p"),
                "courier": courier,
                "user": request.user,
                "logo": static("images/logo/idiotship_logo.png"),
                "manifest_id": f"MANIFEST-{'_'.join(courier.name.split())}-{timestamp.strftime('%Y%m%d_%H%M%S')}",
            },
        )

        # page break between manifests
        if idx > 0:
            all_html += '<div style="page-break-before: always;"></div>'

        all_html += html_fragment

    # Wrap everything inside wrapper template (adds html, body, CSS)
    final_html = render_to_string(
        "order_manager/manifest/manifest_wrapper.dj", {"content": all_html}
    )

    # Generate the final merged PDF
    try:
        pdf_bytes = HTML(
            string=final_html, base_url=request.build_absolute_uri("/")
        ).write_pdf(
            font_config=font_config,
            optimize_size=("images", "fonts"),
            presentational_hints=True,
        )

        filename = f"manifest_{timestamp.strftime('%Y%m%d_%H%M%S')}.pdf".replace(
            "/", "_"
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(pdf_bytes)
        return response

    except Exception as e:
        logger.error(f"Failed to generate manifest: {e}", exc_info=True)
        messages.error(request, "Failed to generate manifest. Try later.")
        return redirect(next_url)


@csrf_exempt
def wordpress_order_created_webhook(request, user_id: str):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    # --------------------------------------------------
    # 1. Fetch User
    # --------------------------------------------------
    try:
        user = User.objects.get(id=user_id)
    except:
        return JsonResponse({"error": "User not found"}, status=404)

    # --------------------------------------------------
    # Verify WooCommerce Website Source
    # --------------------------------------------------
    # incoming_source = request.headers.get("X-WC-Webhook-Source")

    # if not incoming_source:
    #     return JsonResponse(
    #         {"error": "Missing webhook source header"},
    #         status=403,
    #     )

    # # normalize URLs
    # def normalize(url: str):
    #     return url.lower().rstrip("/")

    # if normalize(incoming_source) != normalize(user.woocommerce_website_url):
    #     logger.warning(
    #         f"Webhook rejected. Expected: {user.woocommerce_website_url}, "
    #         f"Received: {incoming_source}"
    #     )
    #     return JsonResponse(
    #         {"error": "Unauthorized WooCommerce source"},
    #         status=403,
    #     )
    # --------------------------------------------------
    # 3. Parse Payload
    # --------------------------------------------------
    try:
        data = json.loads(request.body)
        logger.debug(f"Wordpress webhook payload of user {user.email}: {data}")
    except Exception:
        if request.content_type == "application/x-www-form-urlencoded":
            return HttpResponse("Webhook validated")
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    # --------------------------------------------------
    # 4. Idempotency Protection
    # --------------------------------------------------
    # delivery_id = request.headers.get("X-WC-Webhook-Delivery-ID")

    # --------------------------------------------------
    # 5. Extract Order Data
    # --------------------------------------------------
    try:
        order_number = str(data["id"])
        order_status = data.get("status", "processing")
        total_amount = float(data.get("total", 0))
        discount = float(data.get("discount_total", 0))

        shipping = data.get("shipping", {})
        billing = data.get("billing", {})
        items = data.get("line_items", [])
    except Exception:
        return JsonResponse({"error": "Invalid order structure"})

    # --------------------------------------------------
    # Consignee Details
    # --------------------------------------------------
    name = f"{shipping.get('first_name','')} {shipping.get('last_name','')}".strip()

    # WooCommerce sometimes keeps phone only in billing
    phone = shipping.get("phone") or billing.get("phone") or ""

    # --------------------------------------------------
    # Payment Mapping
    # --------------------------------------------------
    payment_method = "cod" if data.get("payment_method") == "cod" else "prepaid"
    cod_collectable_amount = total_amount if payment_method == "cod" else 0

    # --------------------------------------------------
    # Package Defaults
    # --------------------------------------------------
    weight_in_kg = float(data.get("weight") or 2)
    length_in_cm = float(data.get("length") or 10)
    width_in_cm = float(data.get("width") or 10)
    height_in_cm = float(data.get("height") or 10)

    try:
        with transaction.atomic():
            # --------------------------------------------------
            # 6. Prevent Duplicate Orders
            # --------------------------------------------------
            if Order.objects.filter(user=user, order_number=order_number).exists():
                return HttpResponse("Order already exists")

            # --------------------------------------------------
            # 7. Create Address
            # --------------------------------------------------
            address = Address.objects.create(
                user=user,
                name=name,
                phone=phone[:10],
                line1=shipping.get("address_1", ""),
                line2=shipping.get("address_2", ""),
                city=shipping.get("city", ""),
                state=shipping.get("state", ""),
                pin_code=shipping.get("postcode", ""),
                country=shipping.get("country", "India"),
                company_name=shipping.get("company", ""),
                email=billing.get("email", ""),
            )

            # --------------------------------------------------
            # 8. Create Order
            # --------------------------------------------------
            order = Order.objects.create(
                user=user,
                order_number=order_number,
                shipping_address=address,
                billing_address=address,
                channel="woocommerce",
                status="ready_to_ship",
                total_amount=0,
            )

            total_calculated = 0

            # --------------------------------------------------
            # 9. Create Products + Order Items
            # --------------------------------------------------
            for item in items:
                quantity = float(item.get("quantity", 1))
                total = float(item.get("total", 0))
                sku = item.get("sku") or ""
                name = item.get("name")

                unit_price = (total + discount) / quantity if quantity else 0

                product = Product.objects.create(
                    name=name,
                    sku=sku,
                    price=unit_price,
                    weight_kg=weight_in_kg,
                    length_cm=length_in_cm,
                    width_cm=width_in_cm,
                    height_cm=height_in_cm,
                )

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=int(quantity),
                    unit_price=unit_price,
                    total_price=total,
                    sku_code=sku,
                )

                total_calculated += total

            # --------------------------------------------------
            # 10. Update Order Total
            # --------------------------------------------------
            order.total_amount = total_calculated
            order.save()

            # --------------------------------------------------
            # 11. Create Payment
            # --------------------------------------------------
            Payment.objects.create(
                order=order,
                method=payment_method,
                status="pending",
                amount=order.total_amount,
                cod_collectable_amount=cod_collectable_amount,
            )

            # --------------------------------------------------
            # 12. Create Shipment
            # --------------------------------------------------
            Shipment.objects.create(
                order=order,
                package_weight_kg=weight_in_kg,
                package_length_cm=length_in_cm,
                package_width_cm=width_in_cm,
                package_height_cm=height_in_cm,
                hub=order.hub,
            )

    except Exception as e:
        logger.exception("WooCommerce webhook failed")
        return JsonResponse(
            {"error": f"Order creation failed: {str(e)}"},
            status=500,
        )

    return HttpResponse("OK")
