# shopify_integration/validators/order_validators.py

from django.contrib.auth import get_user_model

from order_manager.models import Order, Hub

User = get_user_model()


class ShopifyOrderValidationError(Exception):
    """
    Raised when a Shopify order fails any pre-creation or pre-processing
    validation check. Caught in webhook_processor.py and converted to a
    structured error response.
    """

    pass


# ─────────────────────────────────────────────────────────────────────────────
# USER & CONNECTION VALIDATORS
# ─────────────────────────────────────────────────────────────────────────────


def validate_user_connected(user_id: int):
    """
    Confirm user exists and has a Shopify access token stored.

    Args:
        user_id: PK of the User to look up.

    Returns:
        User instance if valid.

    Raises:
        ShopifyOrderValidationError if user not found or token missing.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise ShopifyOrderValidationError(f"User with id={user_id} does not exist.")

    if not user.shopify_stores:
        raise ShopifyOrderValidationError(
            f"User {user.email} has no Shopify access token. "
            "Please reconnect the Shopify app."
        )

    return user


# ─────────────────────────────────────────────────────────────────────────────
# IDEMPOTENCY VALIDATOR
# ─────────────────────────────────────────────────────────────────────────────


def validate_not_duplicate(shopify_order_id: str, user) -> None:
    """
    Ensure this Shopify order has not already been imported for this user.

    Uses order_number + channel + user as the unique key.

    Args:
        shopify_order_id: Shopify order ID string (e.g. "5123456789" or "#1005").
        user:             User instance.

    Raises:
        ShopifyOrderValidationError if a matching order already exists.
    """
    if Order.objects.filter(
        order_number=shopify_order_id,
        channel="shopify",
        user=user,
    ).exists():
        raise ShopifyOrderValidationError(
            f"Shopify order '{shopify_order_id}' already exists in the system. "
            "Skipping duplicate."
        )


# ─────────────────────────────────────────────────────────────────────────────
# HUB VALIDATOR
# ─────────────────────────────────────────────────────────────────────────────


def validate_has_hub(user) -> Hub:
    """
    Ensure the user has at least one active pickup hub configured.

    Returns the primary hub (or first active hub if none marked primary).

    Args:
        user: User instance.

    Returns:
        Hub instance.

    Raises:
        ShopifyOrderValidationError if no active hub found.
    """
    hub = Hub.get_primary(user)
    if not hub:
        raise ShopifyOrderValidationError(
            f"User {user.email} has no active pickup hub. "
            "Please create a hub before processing Shopify orders."
        )
    return hub


# ─────────────────────────────────────────────────────────────────────────────
# BALANCE VALIDATOR
# ─────────────────────────────────────────────────────────────────────────────


def validate_has_balance(user, estimated_charge: float) -> None:
    """
    Ensure the user's wallet balance can cover the estimated shipping charge.

    Uses user.have_balance() which accounts for min_balance threshold.

    Args:
        user:              User instance.
        estimated_charge:  Float amount to check against balance.

    Raises:
        ShopifyOrderValidationError if balance is insufficient.
    """
    if not user.have_balance(estimated_charge):
        raise ShopifyOrderValidationError(
            f"Insufficient wallet balance for user {user.email}. "
            f"Required: ₹{estimated_charge:.2f} | "
            f"Available: ₹{user.balance:.2f} | "
            f"Minimum allowed: ₹{user.min_balance:.2f}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# SHIPPING ADDRESS VALIDATOR  (raw Shopify format)
# ─────────────────────────────────────────────────────────────────────────────


def validate_shipping_address(payload: dict) -> dict:
    """
    Validate that a raw Shopify order payload contains a usable shipping address.

    Checks for the presence of 'shipping_address' or falls back to
    'billing_address'. Ensures minimum required fields (city, zip) exist.

    Args:
        payload: Raw Shopify order payload dict.

    Returns:
        The address dict (shipping or billing).

    Raises:
        ShopifyOrderValidationError if address is missing or incomplete.
    """
    addr = payload.get("shipping_address") or payload.get("billing_address") or {}

    if not addr:
        raise ShopifyOrderValidationError(
            "Shopify order has no shipping_address or billing_address."
        )

    required = ["city", "zip"]
    missing = [f for f in required if not addr.get(f)]
    if missing:
        raise ShopifyOrderValidationError(
            f"Shopify shipping_address is missing required fields: {missing}"
        )

    return addr


# ─────────────────────────────────────────────────────────────────────────────
# DEVELOPER PAYLOAD VALIDATOR  (PDF spec format)
# ─────────────────────────────────────────────────────────────────────────────


def validate_developer_payload(payload: dict) -> None:
    """
    Validate the Shopify developer's custom payload format (PDF spec).

    Required top-level fields:
        order_number, total_amount, shipping_address, items, customer

    Required inside shipping_address:
        address, city, state, pincode

    Required inside customer:
        name

    Each item must have:
        name, price

    Args:
        payload: Developer-format payload dict.

    Raises:
        ShopifyOrderValidationError describing exactly which field is missing.
    """
    # Top-level required fields
    required_top = [
        "order_number",
        "total_amount",
        "shipping_address",
        "items",
        "customer",
    ]
    missing_top = [f for f in required_top if not payload.get(f)]
    if missing_top:
        raise ShopifyOrderValidationError(
            f"Payload missing required top-level fields: {missing_top}"
        )

    # Shipping address required fields
    addr = payload.get("shipping_address") or {}
    required_addr = ["address", "city", "state", "pincode"]
    missing_addr = [f for f in required_addr if not addr.get(f)]
    if missing_addr:
        raise ShopifyOrderValidationError(
            f"shipping_address missing required fields: {missing_addr}"
        )

    # Customer required fields
    customer = payload.get("customer") or {}
    if not customer.get("name"):
        raise ShopifyOrderValidationError("Payload missing customer.name.")

    # Items validation
    items = payload.get("items") or []
    if not items:
        raise ShopifyOrderValidationError(
            "Payload has an empty 'items' list. At least one item is required."
        )

    for i, item in enumerate(items):
        if not item.get("name"):
            raise ShopifyOrderValidationError(f"Item at index {i} is missing 'name'.")
        if item.get("price") is None:
            raise ShopifyOrderValidationError(
                f"Item '{item.get('name', i)}' is missing 'price'."
            )


# ─────────────────────────────────────────────────────────────────────────────
# ORDER STATE VALIDATORS
# ─────────────────────────────────────────────────────────────────────────────


def validate_order_cancellable(order) -> None:
    """
    Ensure the order is in a state that permits cancellation.

    Non-cancellable statuses:
        delivered, rto_delivered, lost, damaged, cancelled

    Args:
        order: Order instance.

    Raises:
        ShopifyOrderValidationError if order cannot be cancelled.
    """
    non_cancellable = {"delivered", "rto_delivered", "lost", "damaged", "cancelled"}
    if order.status in non_cancellable:
        raise ShopifyOrderValidationError(
            f"Order #{order.id} cannot be cancelled — "
            f"current status is '{order.status}'."
        )


def validate_order_updatable(order) -> bool:
    """
    Check if the order is still in a mutable state (address/notes can change).

    Mutable statuses: ready_to_ship, processing

    Does NOT raise — returns bool so caller can decide what to do.

    Args:
        order: Order instance.

    Returns:
        True if order fields can still be updated, False otherwise.
    """
    return order.status in {"ready_to_ship", "processing"}


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────


def run_all_create_validations(
    user_id: int,
    shopify_order_id: str,
    payload: dict,
) -> tuple:
    """
    Run every validation required before creating a new order from a raw
    Shopify webhook payload.

    Runs in order:
        1. validate_user_connected
        2. validate_not_duplicate
        3. validate_has_hub
        4. validate_shipping_address

    Args:
        user_id:          PK of the user who owns the Shopify store.
        shopify_order_id: Shopify order ID string.
        payload:          Raw Shopify order payload dict.

    Returns:
        Tuple of (user, hub, address_dict) — all ready to use.

    Raises:
        ShopifyOrderValidationError on the first failing check.
    """
    user = validate_user_connected(user_id)
    validate_not_duplicate(shopify_order_id, user)
    address_dict = validate_shipping_address(payload)

    return user, address_dict
