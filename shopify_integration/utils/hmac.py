# shopify_integration/utils/hmac.py

import base64
import hashlib
import hmac

from django.conf import settings


def verify_webhook_hmac(request, secret: str = None) -> bool:
    """
    Verify a Shopify webhook request using HMAC-SHA256.

    Uses per-merchant secret if provided, falls back to global
    SHOPIFY['WEBHOOK_SECRET'] setting.

    Args:
        request: Django HttpRequest with raw body and headers.
        secret:  Optional per-merchant webhook secret string.

    Returns:
        True if HMAC matches, False otherwise.
    """
    shopify_hmac = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if not shopify_hmac:
        return False

    secret = secret or settings.SHOPIFY["WEBHOOK_SECRET"]

    digest = hmac.new(
        secret.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).digest()

    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, shopify_hmac)


def verify_oauth_hmac(params: dict, store) -> bool:
    """
    Verify the HMAC that Shopify sends during OAuth callback.

    Args:
        params: dict from request.GET.lists() — values are lists.

    Returns:
        True if HMAC matches, False otherwise.
    """
    params = dict(params)  # mutable copy

    # Extract hmac value — handles both list and plain string
    raw = params.pop("hmac", "")
    hmac_value = raw[0] if isinstance(raw, list) else raw

    sorted_params = "&".join(
        f"{k}={v[0] if isinstance(v, list) else v}" for k, v in sorted(params.items())
    )

    digest = hmac.new(
        store.shopify_api_secret.encode(),
        sorted_params.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(digest, hmac_value)


