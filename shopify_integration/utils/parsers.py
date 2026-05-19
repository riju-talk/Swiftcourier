# shopify_integration/utils/parsers.py

import logging
from order_manager.models import Address, Product, OrderItem, Order


logger = logging.getLogger("my-logger")


# ─────────────────────────────────────────────────────────────────────────────
# FORMAT DETECTION
# ─────────────────────────────────────────────────────────────────────────────


def is_developer_payload(payload: dict) -> bool:
    """
    Detect if the incoming payload is the Shopify developer's custom format.

    Developer format (PDF spec) has:
        - 'customer'  key at top level
        - 'items'     key at top level
        - 'pincode'   inside shipping_address

    Raw Shopify webhook format has:
        - 'line_items' key at top level
        - 'zip'        inside shipping_address

    Returns:
        True  → developer custom format
        False → raw Shopify webhook format
    """
    addr = payload.get("shipping_address") or {}
    return "customer" in payload and "items" in payload and "pincode" in addr


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHT HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def grams_to_kg(grams) -> float:
    """Convert grams to kg. Enforces 0.5 kg minimum."""
    kg = round(float(grams or 0) / 1000, 3)
    return max(kg, 0.5)


def total_weight_kg(line_items: list) -> float:
    """
    Sum weight across all raw Shopify line_items.
    Each item contributes grams * quantity.
    Enforces 0.5 kg minimum total.
    """
    total = sum(
        grams_to_kg(item.get("grams", 0)) * int(item.get("quantity") or 1)
        for item in line_items
    )
    return max(round(total, 3), 0.5)


# ─────────────────────────────────────────────────────────────────────────────
# RAW SHOPIFY PAYLOAD PARSERS
# ─────────────────────────────────────────────────────────────────────────────


def is_cod(payload: dict) -> bool:
    """
    Detect if a raw Shopify order is Cash on Delivery.
    Checks payment_gateway field for COD-related keywords.
    """
    if payload.get("financial_status", "").lower() == "partially_paid":
        return True

    gateway = (payload.get("payment_gateway") or payload.get("payment_gateway_names") or [])
    if isinstance(gateway, list):
        gateway = [g.lower() for g in gateway]

    cod_keywords = [
        "cod",
        "cash_on_delivery",
        "cash on delivery",
        "pay_on_delivery",
        "cash on delivery (cod)",
    ]
    return any(kw in gateway for kw in cod_keywords)


def get_total_amount(payload: dict) -> float:
    """Extract order total price from raw Shopify payload."""
    return float(payload.get("total_price") or 0.0)


def parse_shipping_address(shopify_address: dict, user) -> Address:
    """
    Convert a raw Shopify shipping_address dict into an unsaved Address instance.

    Raw Shopify keys used:
        name, address1, address2, company, city, province,
        zip, country, phone, email

    Caller must call .save() inside a transaction.

    Args:
        shopify_address: dict from payload['shipping_address']
        user:            User instance (ForeignKey on Address)

    Returns:
        Unsaved Address instance.
    """
    phone = (shopify_address.get("phone") or "")[:10]
    pin_code = (shopify_address.get("zip") or "000000")[:6]

    return Address(
        user=user,
        name=shopify_address.get("name", ""),
        label="shopify",
        line1=shopify_address.get("address1") or "",
        line2=shopify_address.get("address2") or "",
        landmark="",
        company_name=shopify_address.get("company") or "",
        city=shopify_address.get("city") or "",
        state=shopify_address.get("province") or "",
        pin_code=pin_code,
        country=shopify_address.get("country") or "India",
        phone=phone,
        alt_phone="",
        email=shopify_address.get("email") or "",
    )


def parse_line_items(line_items: list, order: Order) -> list:
    """
    Convert raw Shopify line_items into Product + OrderItem rows.

    For each item:
        - Reuses existing Product if SKU already exists.
        - Creates new Product if not found.
        - Creates and saves an OrderItem linked to the order.

    Args:
        line_items: list from payload['line_items']
        order:      Order instance (already saved)

    Returns:
        List of created OrderItem instances.
    """
    created = []

    for item in line_items:
        shopify_variant_id = str(item.get("variant_id") or "")
        shopify_product_id = str(item.get("product_id") or "")
        sku = item.get("sku") or shopify_variant_id or shopify_product_id

        product = Product.objects.create(
            sku=sku,
            name=item.get("title") or "Shopify Product",
            description=item.get("variant_title") or "",
            weight_kg=grams_to_kg(item.get("grams", 0)),
            length_cm=10,
            width_cm=10,
            height_cm=10,
            price=float(item.get("price") or 0.0),
        )

        quantity = int(item.get("quantity") or 1)
        unit_price = float(item.get("price") or 0.0)

        order_item = OrderItem(
            order=order,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            total_price=round(unit_price * quantity, 2),
            sku_code=sku,
        )
        order_item.save()
        created.append(order_item)

    return created


def update_address_from_shopify(address: Address, shopify_address: dict) -> Address:
    """
    Patch an existing Address instance with updated Shopify address data.

    Only updates fields that are present in the new payload.
    Does NOT call .save() — caller must save inside a transaction.

    Args:
        address:         Existing Address instance to update.
        shopify_address: New address dict from Shopify webhook payload.

    Returns:
        Updated (unsaved) Address instance.
    """
    address.name = shopify_address.get("name", address.name)
    address.line1 = shopify_address.get("address1", address.line1)
    address.line2 = shopify_address.get("address2", address.line2)
    address.city = shopify_address.get("city", address.city)
    address.state = shopify_address.get("province", address.state)
    address.pin_code = (shopify_address.get("zip") or address.pin_code)[:6]
    address.phone = (shopify_address.get("phone") or address.phone)[:10]
    address.company_name = shopify_address.get("company", address.company_name)
    return address


# ─────────────────────────────────────────────────────────────────────────────
# DEVELOPER CUSTOM PAYLOAD PARSERS  (PDF spec format)
# ─────────────────────────────────────────────────────────────────────────────


def parse_developer_shipping_address(payload: dict, user) -> Address:
    """
    Convert the developer's custom shipping_address format into an unsaved Address.

    Developer format (from PDF spec):
    {
        "customer": {"name": "pritam kumar", "email": "..."},
        "shipping_address": {
            "address": "Gurmail nagar lohara...",
            "city":    "Ludhiana",
            "state":   "Punjab",
            "pincode": "141003",
            "country": "India",
            "phone":   "+918210581348"
        }
    }

    Differences from raw Shopify format:
        - 'address'  instead of 'address1'
        - 'pincode'  instead of 'zip'
        - 'state'    instead of 'province'
        - name comes from 'customer.name' not 'shipping_address.name'
        - phone may include +91 country code prefix

    Caller must call .save() inside a transaction.
    """
    addr = payload.get("shipping_address") or {}
    customer = payload.get("customer") or {}

    # Strip +91 or +XX country code, keep last 10 digits
    raw_phone = (addr.get("phone") or "").strip().replace(" ", "")
    if raw_phone.startswith("+91"):
        raw_phone = raw_phone[3:]
    elif raw_phone.startswith("+"):
        raw_phone = raw_phone[1:]
    phone = raw_phone[-10:] if len(raw_phone) >= 10 else raw_phone

    pin_code = (addr.get("pincode") or "000000")[:6]

    return Address(
        user=user,
        name=customer.get("name", ""),
        label="shopify",
        line1=addr.get("address") or "",
        line2="",
        landmark="",
        company_name="",
        city=addr.get("city") or "",
        state=addr.get("state") or "",
        pin_code=pin_code,
        country=addr.get("country") or "India",
        phone=phone,
        alt_phone="",
        email=customer.get("email") or "",
    )


def parse_developer_line_items(payload: dict, order: Order) -> list:
    """
    Convert developer 'items' list into Product + OrderItem rows.

    Developer format:
    "items": [
        {"name": "ATHEN - 32", "quantity": 1, "price": 2799.0}
    ]

    Differences from raw Shopify format:
        - No SKU field  → generated from product name
        - No weight     → defaults to 0.5 kg per item
        - No variant/product IDs

    Args:
        payload: Full developer payload dict.
        order:   Order instance (already saved).

    Returns:
        List of created OrderItem instances.
    """
    items = payload.get("items") or []
    created = []

    for item in items:
        name = item.get("name") or "Shopify Product"
        quantity = int(item.get("quantity") or 1)
        price = float(item.get("price") or 0.0)

        # Generate a stable, unique SKU from product name
        sku = "SHOP-" + name.upper().replace(" ", "-").replace("/", "-")[:40]

        product, _ = Product.objects.get_or_create(
            sku=sku,
            defaults={
                "name": name,
                "description": "",
                "weight_kg": 0.5,  # developer payload provides no weight
                "length_cm": 1,
                "width_cm": 1,
                "height_cm": 1,
                "price": price,
                "stock": 999,
                "active": True,
            },
        )

        order_item = OrderItem(
            order=order,
            product=product,
            quantity=quantity,
            unit_price=price,
            total_price=round(price * quantity, 2),
            sku_code=sku,
        )
        order_item.save()
        created.append(order_item)

    return created


def parse_developer_payload_to_standard(payload: dict) -> dict:
    """
    Normalize the developer's custom payload into a standard internal dict
    used throughout webhook_processor.py.

    Args:
        payload: Full developer payload dict.

    Returns:
        Dict with normalized fields:
            shopify_order_id, total_amount, invoice_amount,
            is_cod, weight_kg, notes, raw
    """
    items = payload.get("items") or []
    total_qty = sum(int(i.get("quantity") or 1) for i in items)

    return {
        "shopify_order_id": str(payload.get("order_number") or ""),
        "total_amount": float(payload.get("total_amount") or 0.0),
        "invoice_amount": float(payload.get("invoice_amount") or 0.0),
        # Developer payload has no payment_gateway → default prepaid
        "is_cod": False,
        # 0.5 kg per item as default since no weight is provided
        "weight_kg": max(0.5 * total_qty, 0.5),
        "notes": "",
        "raw": payload,
    }
