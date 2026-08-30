import csv
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.db.models import QuerySet

from .models import Order


# =========================
# HEADERS
# =========================
HEADERS = [
    "IdiotShip Order ID",
    "Courier",
    "AWB No",
    "Status",
    "Order ID",
    "Booked At",
    "Picked At",
    "Delivered At",
    "RTO Delivered At",
    "Payment Type",
    "COD Value",
    "Order Value",
    # HUB
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
    # SHIPPING
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
    # SHIPMENT
    "Weight(Kg)",
    "Length(cm)",
    "Breadth(cm)",
    "Height(cm)",
    "Shipping Charges",
    "COD Charges",
    "Discount",
]

for i in range(1, 11):
    HEADERS.extend(
        [
            f"SKU({i})",
            f"Product({i})",
            f"Quantity({i})",
            f"Per Product Price({i})",
            f"Product Price({i})",
        ]
    )


# =========================
# STREAM HELPER
# =========================
class Echo:
    """Acts like a file but returns value instead of storing it"""

    def write(self, value):
        return value


# =========================
# MAIN EXPORT FUNCTION
# =========================
def generate_bulk_export_response(
    orders: QuerySet[Order],
    filename: str = "swiftcourier_bulk_orders_export",
):
    """
    Optimized CSV export:
    - Streams response (no memory overload)
    - Optimized DB queries
    - Safe for large datasets
    """

    # =========================
    # QUERY OPTIMIZATION
    # =========================
    orders = (
        orders.select_related(
            "payment",
            "shipping_address",
            "hub",
            "shipment",
            "logistic_partner",
        )
        .prefetch_related("items__product")
        .iterator(chunk_size=500)
    )

    pseudo_buffer = Echo()
    writer = csv.writer(pseudo_buffer)

    # =========================
    # GENERATOR FUNCTION
    # =========================
    def generate():
        # Header row
        yield writer.writerow(HEADERS)

        for order in orders:
            payment = order.payment
            shipping_address = order.shipping_address
            pickup_address = order.hub
            shipment = order.shipment

            # Already prefetched → no extra query
            order_items = list(order.items.all())

            row = [
                order.id,
                order.logistic_partner.name if order.logistic_partner else "",
                order.awb_number or "",
                order.get_status_display(),
                order.order_number or "",
                (
                    shipment.booked_at.strftime("%d-%m-%Y %H:%M:%S")
                    if shipment and shipment.booked_at
                    else ""
                ),
                (
                    shipment.shipped_at.strftime("%d-%m-%Y %H:%M:%S")
                    if shipment and shipment.shipped_at
                    else ""
                ),
                (
                    shipment.delivered_at.strftime("%d-%m-%Y %H:%M:%S")
                    if order.status == "delivered"
                    and shipment
                    and shipment.delivered_at
                    else ""
                ),
                (
                    shipment.rto_delivered_at.strftime("%d-%m-%Y %H:%M:%S")
                    if order.status == "rto_delivered"
                    and shipment
                    and shipment.rto_delivered_at
                    else ""
                ),
                payment.get_method_display() if payment else "",
                order.total_amount if payment and payment.method == "cod" else "0",
                order.total_amount if payment else "",
                # HUB
                pickup_address.contact_person if pickup_address else "",
                pickup_address.address_line1 if pickup_address else "",
                pickup_address.address_line2 if pickup_address else "",
                pickup_address.phone if pickup_address else "",
                pickup_address.alt_phone if pickup_address else "",
                pickup_address.email if pickup_address else "",
                pickup_address.pin_code if pickup_address else "",
                pickup_address.city if pickup_address else "",
                pickup_address.state if pickup_address else "",
                pickup_address.country if pickup_address else "",
                # SHIPPING
                shipping_address.name if shipping_address else "",
                shipping_address.email if shipping_address else "",
                shipping_address.company_name if shipping_address else "",
                shipping_address.line1 if shipping_address else "",
                shipping_address.line2 if shipping_address else "",
                shipping_address.phone if shipping_address else "",
                shipping_address.alt_phone if shipping_address else "",
                shipping_address.pin_code if shipping_address else "",
                shipping_address.city if shipping_address else "",
                shipping_address.state if shipping_address else "",
                shipping_address.country if shipping_address else "",
                # SHIPMENT
                shipment.package_weight_kg if shipment else "",
                shipment.package_length_cm if shipment else "",
                shipment.package_width_cm if shipment else "",
                shipment.package_height_cm if shipment else "",
                payment.shipping_charges if payment else "",
                payment.cod_charges if payment else "",
                payment.discount if payment else "",
            ]

            # =========================
            # ITEMS (MAX 10)
            # =========================
            for item in order_items[:10]:
                row.extend(
                    [
                        item.product.sku if item.product else "",
                        item.product.name if item.product else "",
                        item.quantity,
                        item.unit_price,
                        item.total_price,
                    ]
                )

            # Fill remaining item columns if < 10
            remaining = 10 - len(order_items[:10])
            for _ in range(remaining):
                row.extend(["", "", "", "", ""])

            yield writer.writerow(row)

    # =========================
    # RESPONSE
    # =========================
    response = StreamingHttpResponse(
        generate(),
        content_type="text/csv",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    )

    return response
