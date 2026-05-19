from datetime import datetime

from openpyxl import Workbook
from django.db.models import Prefetch
from django.utils.timezone import localtime, now


def export_orders_to_xlsx(file_path="monthly_mis.xlsx"):
    # ---------------------------------------------------
    # Headers
    # ---------------------------------------------------
    headers = [
        "Created At",
        "IdiotShip Order ID",
        "Email",
        "User Code",
        "Courier",
        "AWB No",
        "Cancelled AWB Nos",
        "Status",
        "Order ID",
        "Booked At",
        "Picked At",
        "Delivered At",
        "RTO Delivered At",
        "Payment Type",
        "COD Amount",
        "Hub Contact Person Name",
        "Hub Address Line 1",
        "Hub Address Line 2",
        "Hub Mobile No",
        "Hub Alternate No",
        "Hub Email",
        "Hub Pincode",
        "Hub City",
        "Hub State",
        "Hub Country",
        "First Name",
        "Email",
        "Company Name",
        "Address 1",
        "Address 2",
        "Mobile",
        "Alternate phone",
        "Pincode",
        "City",
        "State",
        "Country",
        "Weight(Kg)",
        "Length(cm)",
        "Breadth(cm)",
        "Height(cm)",
        "Shipping Charges",
        "COD Charges",
        "Discount",
    ]
    # Product headers
    for i in range(1, 11):
        headers.extend(
            [
                f"SKU({i})",
                f"Product({i})",
                f"Quantity({i})",
                f"Per Product Price({i})",
                f"Total Price({i})",
            ]
        )
    # ---------------------------------------------------
    # Optimized Query
    # ---------------------------------------------------
    orders = (
        Order.objects.filter(
            created_at__date__gte=datetime(2026, 5, 1),
            created_at__date__lte=datetime(2026, 6, 1),
        )
        .select_related("shipment", "logistic_partner")
        .prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.all().order_by("id"))
        )
    )
    # ---------------------------------------------------
    # Create Workbook
    # ---------------------------------------------------
    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"
    ws.append(headers)
    # ---------------------------------------------------
    # Helper function
    # ---------------------------------------------------
    def format_dt(dt):
        return localtime(dt).strftime("%Y-%m-%d %H:%M:%S") if dt else ""
    # ---------------------------------------------------
    # Loop Orders
    # ---------------------------------------------------
    for order in orders:
        shipment = getattr(order, "shipment", None)
        items = list(order.items.all())
        row = [
            # Order Basic
            format_dt(order.created_at),
            order.get_order_id(),
            order.user.email,
            order.user.shipzee_code,
            order.logistic_partner.name if order.logistic_partner else "",
            order.awb_number,
            ",".join(order.cancel_data) if order.cancel_data else "",
            order.get_status_display(),
            order.order_number,
            format_dt(shipment.booked_at),
            format_dt(shipment.shipped_at if shipment else None),
            format_dt(shipment.delivered_at if shipment else None),
            format_dt(shipment.rto_delivered_at if shipment else None),
            order.payment.method,
            order.total_amount if order.payment.method == "cod" else 0,
            # Hub Details
            order.hub.contact_person if order.hub else "",
            order.hub.address_line1 if order.hub else "",
            order.hub.address_line2 if order.hub else "",
            order.hub.phone if order.hub else "",
            order.hub.alt_phone if order.hub else "",
            order.hub.email if order.hub else "",
            order.hub.pin_code if order.hub else "",
            order.hub.city if order.hub else "",
            order.hub.state if order.hub else "",
            order.hub.country if order.hub else "",
            # Customer Details
            order.shipping_address.name if order.shipping_address else "",
            order.shipping_address.email if order.shipping_address else "",
            order.shipping_address.company_name if order.shipping_address else "",
            order.shipping_address.line1 if order.shipping_address else "",
            order.shipping_address.line2 if order.shipping_address else "",
            order.shipping_address.phone if order.shipping_address else "",
            order.shipping_address.alt_phone if order.shipping_address else "",
            order.shipping_address.pin_code if order.shipping_address else "",
            order.shipping_address.city if order.shipping_address else "",
            order.shipping_address.state if order.shipping_address else "",
            order.shipping_address.country if order.shipping_address else "",
            # Parcel
            shipment.package_weight_kg,
            shipment.package_length_cm,
            shipment.package_width_cm,
            shipment.package_height_cm,
            order.payment.shipping_charges,
            order.payment.cod_charges,
            order.payment.discount,
        ]
        # ---------------------------------------------------
        # Product Data (Max 10)
        # ---------------------------------------------------
        for i in range(10):
            if i < len(items):
                item = items[i]
                row.extend(
                    [
                        item.sku_code,
                        item.product.name,
                        item.quantity,
                        item.unit_price,
                        item.total_price,
                    ]
                )
            else:
                row.extend(["", "", "", "", ""])
        ws.append(row)
    wb.save(file_path)
    return file_path

export_orders_to_xlsx(
    "all_time_may_mis_4.xlsx"
)
