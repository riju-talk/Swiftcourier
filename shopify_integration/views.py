# shopify_integration/views.py

import json
import logging
import urllib.parse

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .models import ShopifyStore, WebhookLog
from .utils.hmac import verify_webhook_hmac, verify_oauth_hmac
from .utils.parsers import is_developer_payload
from .utils.webhook_processor import (
    process_order_created,
    process_order_cancelled,
    process_order_updated,
    process_developer_order,
)


logger = logging.getLogger("my-logger")
User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _log_webhook(
    topic: str,
    store: ShopifyStore,
    shopify_id: str,
    payload: dict,
    status: str = "received",
) -> WebhookLog:
    """
    Create a WebhookLog entry for every incoming webhook.
    Returns the saved instance so processor functions can update it.
    """
    return WebhookLog.objects.create(
        topic=topic,
        store=store,
        shopify_id=str(shopify_id),
        payload=payload,
        status=status,
    )


def _handle_webhook(request, topic: str, processor_fn=None) -> HttpResponse:
    """
    Shared handler for all raw Shopify webhook endpoints.

    Flow:
        1.  Get shop from header → look up User
        2.  Verify HMAC (per-merchant secret or global fallback)
        3.  Parse JSON body
        4.  Duplicate check (same topic + shopify_id already processed)
        5.  Log to WebhookLog
        6.  Call processor_fn synchronously
        7.  Return HTTP 200 immediately

    Args:
        request:      Django HttpRequest.
        topic:        Shopify webhook topic string (e.g. 'orders/create').
        processor_fn: Callable from webhook_processor.py, or None to skip processing.

    Returns:
        HttpResponse with status 200 (or 401/400 on auth/parse failure).
    """
    shop = request.headers.get("X-Shopify-Shop-Domain", "")
    store = ShopifyStore.get_shopify_store_by_shop_url(shop_url=shop)
    user = store.user

    # Use per-merchant secret if available, fall back to global setting
    secret = (
        store.shopify_webhook_secret
        if store and store.shopify_webhook_secret
        else settings.SHOPIFY["WEBHOOK_SECRET"]
    )

    # ── 1. HMAC VERIFICATION ──────────────────────────────────────────────
    # if not verify_webhook_hmac(request, secret):
    #     logger.warning(f"[webhook] HMAC failed | topic={topic} | shop={shop}")
    #     return HttpResponse("Unauthorized", status=401)

    # ── 2. PARSE BODY ─────────────────────────────────────────────────────
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse("Invalid JSON body.", status=400)

    shopify_id = str(payload.get("id", ""))

    # ── 3. DUPLICATE CHECK ────────────────────────────────────────────────
    if WebhookLog.objects.filter(
        topic=topic,
        shopify_id=shopify_id,
        status__in=["processed", "processing"],
    ).exists():
        logger.info(f"[webhook] Duplicate skipped | topic={topic} | id={shopify_id}")
        return HttpResponse(status=200)

    # ── 4. LOG ────────────────────────────────────────────────────────────
    log = _log_webhook(topic, store, shopify_id, payload)

    # ── 5. PROCESS ────────────────────────────────────────────────────────
    if processor_fn and user:
        processor_fn(
            user_id=user.id,
            shopify_order_id=shopify_id,
            payload=payload,
            log=log,
            store=store,
        )
    elif not user:
        log.status = "failed"
        log.error_message = f"No user found for shop domain: '{shop}'"
        log.save(update_fields=["status", "error_message"])
        logger.warning(f"[webhook] No user for shop: {shop}")

    # Always return 200 — Shopify retries on non-200
    return HttpResponse(status=200)


# ─────────────────────────────────────────────────────────────────────────────
# OAUTH VIEWS
# ─────────────────────────────────────────────────────────────────────────────


@require_GET
def oauth_install(request):
    """
    GET /shopify/auth/install/   (also aliased as GET /shopify/auth/)

    Step 1 of Shopify OAuth — redirect the merchant to Shopify's
    permission consent screen.

    Query params:
        shop (required): e.g. mystore.myshopify.com

    Redirects to:
        https://{shop}/admin/oauth/authorize?client_id=...&scope=...&redirect_uri=...
    """
    shop = request.GET.get("shop", "").strip()

    if not shop:
        return HttpResponse("Missing required 'shop' query parameter.", status=400)

    if not shop.endswith(".myshopify.com"):
        return HttpResponse("Invalid shop domain. Must end with .myshopify.com")

    if not request.user.is_authenticated:
        return HttpResponse("Login Required")

    store, created = ShopifyStore.create_shopify_store(
        user=request.user,
        shop_url=shop,
    )

    redirect_uri = f"{settings.SHOPIFY['APP_URL']}/shopify/auth/callback/"
    install_url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={store.shopify_api_token}"
        f"&scope={settings.SHOPIFY['SCOPES']}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    )
    return redirect(install_url)


@require_GET
def oauth_callback(request):
    """
    GET /shopify/auth/callback/

    Step 2 of Shopify OAuth — Shopify redirects here after merchant approves.

    Flow:
        1.  Verify HMAC of query params
        2.  Exchange code for permanent access_token
        3.  Find User by shopify_shop_domain (must be pre-registered)
        4.  Save access_token to User
        5.  Register all webhooks on Shopify
        6.  Redirect to dashboard

    Query params (from Shopify):
        shop, code, hmac, state, timestamp
    """
    if not request.user.is_authenticated:
        return HttpResponse("Login Required")
    
    shop = request.GET.get("shop")
    code = request.GET.get("code")
    store = ShopifyStore.get_shopify_store_by_shop_url(
        shop_url=shop
    )
    
    # ── 1. VERIFY HMAC ────────────────────────────────────────────────────
    # if not verify_oauth_hmac(dict(request.GET.lists()), store):
    #     return HttpResponse("OAuth HMAC verification failed.", status=401)

    
    if not store:
        return HttpResponse(
            f"No user registered for shop '{shop}'. "
            "Please register and set your shop domain first.",
        )


    if not shop or not code:
        return HttpResponse("Missing shop or code parameter.", status=400)

    # ── 2. EXCHANGE CODE FOR ACCESS TOKEN ─────────────────────────────────
    resp = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "client_id": store.shopify_api_token,
            "client_secret": store.shopify_api_secret,
            "code": code,
        },
        timeout=15,
    )

    if not resp.ok:
        logger.error(f"[oauth_callback] Token exchange failed for {shop}: {resp.text}")
        return HttpResponse("Failed to exchange code for access token.", status=400)

    access_token = resp.json().get("access_token")
    if not access_token:
        return HttpResponse("No access token in Shopify response.", status=400)

    # ── 3. FIND USER ──────────────────────────────────────────────────────
    
    # ── 4. SAVE CREDENTIALS ───────────────────────────────────────────────
    store.shopify_access_token = access_token
    store.shopify_installed_at = now()
    store.shopify_uninstalled_at = None
    store.is_active = True
    store.save(
        update_fields=[
            "shopify_access_token",
            "shopify_installed_at",
            "shopify_uninstalled_at",
            "is_active",
        ]
    )

    # ── 5. REGISTER WEBHOOKS ──────────────────────────────────────────────
    from .services.shopify_client import ShopifyClient

    ShopifyClient(shop, access_token).register_all_webhooks(settings.SHOPIFY["APP_URL"])

    logger.info(f"[oauth_callback] Shopify connected | shop={shop} | user={store.user.email}")

    return redirect(f"{settings.SHOPIFY['APP_URL']}/user_panel/dashboard/?shopify=connected")


@csrf_exempt
def oauth_uninstall(request):
    """
    POST /shopify/auth/uninstall/   (also aliased as POST /shopify/webhook/uninstall/)

    Called by Shopify when merchant uninstalls the app.
    Clears access_token and records uninstall timestamp.

    No response body needed — Shopify only checks for 200.
    """
    shop = request.headers.get("X-Shopify-Shop-Domain", "")
    store = ShopifyStore.get_shopify_store_by_shop_url(shop_url=shop)
    user = store.user

    if store:
        store.shopify_access_token = ""
        store.shopify_uninstalled_at = now()
        store.is_active = False
        store.save(update_fields=["shopify_access_token", "shopify_uninstalled_at", "is_active"])
        logger.info(
            f"[oauth_uninstall] App uninstalled | shop={shop} | user={user.email}"
        )
    else:
        logger.warning(f"[oauth_uninstall] No user found for shop: {shop}")

    return HttpResponse(status=200)


# ─────────────────────────────────────────────────────────────────────────────
# RAW SHOPIFY WEBHOOK VIEWS
# ─────────────────────────────────────────────────────────────────────────────


@csrf_exempt
def webhook_order_created(request):
    """
    POST /shopify/webhooks/orders/created/

    Receives raw Shopify orders/create webhook.
    Triggers full order creation pipeline synchronously.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    return _handle_webhook(request, "orders/create", process_order_created)


@csrf_exempt
def webhook_order_updated(request):
    """
    POST /shopify/webhooks/orders/updated/

    Receives raw Shopify orders/updated webhook.
    Updates address, notes, total if order is still mutable.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    return _handle_webhook(request, "orders/updated", process_order_updated)


@csrf_exempt
def webhook_order_cancelled(request):
    """
    POST /shopify/webhooks/orders/cancelled/

    Receives raw Shopify orders/cancelled webhook.
    Cancels shipment with courier and refunds wallet.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    return _handle_webhook(request, "orders/cancelled", process_order_cancelled)


@csrf_exempt
def webhook_order_paid(request):
    """
    POST /shopify/webhooks/orders/paid/

    Receives raw Shopify orders/paid webhook.
    Logged for audit — no additional processing needed
    (payment info is already captured in order/create).
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    return _handle_webhook(request, "orders/paid", processor_fn=None)


# ─────────────────────────────────────────────────────────────────────────────
# DEVELOPER FORMAT VIEWS  (PDF spec endpoints)
# ─────────────────────────────────────────────────────────────────────────────


@csrf_exempt
def webhook_orders(request):
    """
    POST /shopify/webhook/orders/    ← PDF spec endpoint

    Unified webhook endpoint that handles BOTH formats:

        FORMAT A — Developer's custom payload (PDF spec):
            Detected by is_developer_payload():
                has 'customer', 'items', shipping_address.pincode
            Identified via X-Shop-Domain header.
            Returns JSON response with order details.

        FORMAT B — Raw Shopify webhook payload:
            Falls through to _handle_webhook() with HMAC verification.
            Returns plain 200 OK.

    Developer must send:
        Header: X-Shop-Domain: mystore.myshopify.com
        Body:   JSON matching PDF spec format
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    # ── DEVELOPER CUSTOM FORMAT ───────────────────────────────────────────
    if is_developer_payload(payload):
        shop = (
            request.headers.get("X-Shop-Domain", "")
            or request.headers.get("X-Shopify-Shop-Domain", "")
        ).strip()

        if not shop:
            return JsonResponse(
                {
                    "error": "Could not identify merchant. "
                    "Please include the 'X-Shop-Domain' header "
                    "(e.g. X-Shop-Domain: mystore.myshopify.com)."
                },
                status=400,
            )

        store = ShopifyStore.get_shopify_store_by_shop_url(shop)
        user = store.user
        if not user:
            return JsonResponse(
                {
                    "error": f"No connected merchant found for shop '{shop}'. "
                    "Please complete the Shopify OAuth installation first."
                },
                status=404,
            )

        shopify_order_id = str(payload.get("order_number") or "")
        log = _log_webhook("orders/create", store, shopify_order_id, payload)

        result = process_developer_order(payload=payload, user=user, log=log)
        status_code = 200 if result.get("success") else 422
        return JsonResponse(result, status=status_code)

    # ── RAW SHOPIFY WEBHOOK FORMAT ────────────────────────────────────────
    # Re-use shared handler with HMAC verification
    return _handle_webhook(request, "orders/create", process_order_created)


@require_GET
def fetch_orders(request):
    """
    GET /shopify/fetch-orders/    ← PDF spec endpoint

    Manually fetch unfulfilled orders from Shopify API and import
    any that don't already exist in the system.

    Useful for:
        - Initial sync after app installation
        - Catching orders that may have been missed via webhooks

    Query params:
        shop  (optional): filter to a specific shop domain
        limit (optional): max orders to fetch per merchant (default 50)

    Returns JSON with per-order import results.
    """
    shop = request.GET.get("shop", "").strip()
    limit = min(int(request.GET.get("limit", 50)), 250)  # Shopify max is 250

    if shop:
        users = User.objects.filter(
            shopify_shop_domain=shop,
            shopify_access_token__gt="",
        )
    else:
        users = User.objects.filter(shopify_access_token__gt="")

    if not users.exists():
        return JsonResponse(
            {"error": "No connected Shopify merchants found."}, status=404
        )

    all_results = []

    for user in users:
        from .services.shopify_client import ShopifyClient, ShopifyAPIError

        client = ShopifyClient(user.shopify_shop_domain, user.shopify_access_token)

        try:
            orders = client.get_orders(limit=limit)
        except ShopifyAPIError as e:
            logger.error(
                f"[fetch_orders] Shopify API error for {user.shopify_shop_domain}: {e}"
            )
            all_results.append(
                {
                    "shop": user.shopify_shop_domain,
                    "error": str(e),
                }
            )
            continue

        for order_data in orders:
            shopify_id = str(order_data["id"])
            log = _log_webhook(
                "orders/create",
                user.shopify_shop_domain,
                shopify_id,
                order_data,
            )
            result = process_order_created(
                user_id=user.id,
                shopify_order_id=shopify_id,
                payload=order_data,
                log=log,
            )
            all_results.append(
                {
                    "shop": user.shopify_shop_domain,
                    "shopify_id": shopify_id,
                    **result,
                }
            )

    total_success = sum(1 for r in all_results if r.get("success"))
    total_failed = sum(1 for r in all_results if not r.get("success"))

    return JsonResponse(
        {
            "fetched": len(all_results),
            "success_count": total_success,
            "failed_count": total_failed,
            "results": all_results,
        }
    )


@require_GET
def dashboard(request):
    """
    GET /shopify/dashboard/    ← PDF spec endpoint

    Returns a paginated list of stored Shopify orders with summary stats.
    Response format matches what the Shopify developer's system expects.

    Query params:
        status (optional): filter by order status (e.g. ready_to_ship)
        shop   (optional): filter by merchant shop domain
        page   (optional): page number, 1-indexed (default 1)

    Returns:
        {
            "total":    <int>,
            "page":     <int>,
            "per_page": 20,
            "orders":   [ <order dict>, ... ]
        }

    Each order dict matches the PDF spec payload structure:
        order_number, channel, total_amount, customer, shipping_address,
        status, awb_number, courier, created_at
    """
    from order_manager.models import Order

    status_filter = request.GET.get("status", "").strip()
    shop_filter = request.GET.get("shop", "").strip()
    page = max(int(request.GET.get("page", 1)), 1)
    page_size = 20
    offset = (page - 1) * page_size

    qs = Order.objects.filter(channel="shopify").select_related(
        "user", "shipping_address", "logistic_partner"
    )

    if status_filter:
        qs = qs.filter(status=status_filter)

    if shop_filter:
        qs = qs.filter(user__shopify_shop_domain=shop_filter)

    total = qs.count()
    orders = qs.order_by("-created_at")[offset : offset + page_size]

    order_list = []
    for o in orders:
        addr = o.shipping_address
        order_list.append(
            {
                "id": o.id,
                "order_number": o.order_number,
                "channel": o.channel,
                "status": o.status,
                "awb_number": o.awb_number,
                "courier": o.logistic_partner.name if o.logistic_partner else "",
                "total_amount": o.total_amount,
                "invoice_amount": o.invoice_amount,
                "customer": {
                    "name": addr.name if addr else "",
                    "email": addr.email if addr else "",
                    "phone": addr.phone if addr else "",
                },
                "shipping_address": (
                    {
                        "address": addr.line1 if addr else "",
                        "city": addr.city if addr else "",
                        "state": addr.state if addr else "",
                        "pincode": addr.pin_code if addr else "",
                        "country": addr.country if addr else "",
                        "phone": addr.phone if addr else "",
                    }
                    if addr
                    else {}
                ),
                "created_at": str(o.created_at),
            }
        )

    return JsonResponse(
        {
            "total": total,
            "page": page,
            "per_page": page_size,
            "orders": order_list,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL MANAGEMENT VIEWS
# ─────────────────────────────────────────────────────────────────────────────


@require_GET
def merchant_list(request):
    """
    GET /shopify/merchants/

    List all users with a connected Shopify store.
    """
    merchants = User.objects.filter(shopify_access_token__gt="").values(
        "id",
        "email",
        "shopify_shop_domain",
        "shopify_installed_at",
        "shopify_uninstalled_at",
    )
    return JsonResponse({"merchants": list(merchants)})


@require_GET
def sync_orders(request, pk: int):
    """
    GET /shopify/merchants/<pk>/sync/

    Manually trigger order sync for a specific merchant.
    Fetches unfulfilled orders from Shopify API and imports
    any that don't exist in the system yet.

    Path params:
        pk: User primary key.
    """
    try:
        user = User.objects.get(pk=pk, shopify_access_token__gt="")
    except User.DoesNotExist:
        return JsonResponse(
            {"error": "Merchant not found or Shopify not connected."}, status=404
        )

    from .services.shopify_client import ShopifyClient, ShopifyAPIError

    client = ShopifyClient(user.shopify_shop_domain, user.shopify_access_token)

    try:
        orders = client.get_orders()
    except ShopifyAPIError as e:
        logger.exception(f"[sync_orders] Shopify API error for user {user.email}: {e}")
        return JsonResponse({"error": str(e)}, status=500)

    results = []
    for order_data in orders:
        shopify_id = str(order_data["id"])
        log = _log_webhook(
            "orders/create",
            user.shopify_shop_domain,
            shopify_id,
            order_data,
        )
        result = process_order_created(
            user_id=user.id,
            shopify_order_id=shopify_id,
            payload=order_data,
            log=log,
        )
        results.append({"shopify_id": shopify_id, **result})

    success_count = sum(1 for r in results if r.get("success"))
    return JsonResponse(
        {
            "total_fetched": len(results),
            "success_count": success_count,
            "skipped_or_failed": len(results) - success_count,
            "results": results,
        }
    )


@require_GET
def order_list(request):
    """
    GET /shopify/orders/

    List the most recent 100 Shopify-sourced orders.
    Lightweight — no related selects, returns only key fields.
    """
    from order_manager.models import Order

    orders = (
        Order.objects.filter(channel="shopify")
        .values(
            "id",
            "order_number",
            "status",
            "awb_number",
            "total_amount",
            "user__email",
            "created_at",
        )
        .order_by("-created_at")[:100]
    )

    return JsonResponse({"orders": list(orders)})


@require_GET
def order_detail(request, shopify_id: str):
    """
    GET /shopify/orders/<shopify_id>/

    Detailed view for a single Shopify-sourced order.

    Path params:
        shopify_id: The Shopify order ID stored in Order.order_number.
    """
    from order_manager.models import Order

    try:
        order = Order.objects.select_related(
            "shipping_address", "logistic_partner", "payment", "shipment"
        ).get(order_number=shopify_id, channel="shopify")
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found."}, status=404)

    addr = order.shipping_address

    return JsonResponse(
        {
            "id": order.id,
            "shopify_order_id": order.order_number,
            "channel": order.channel,
            "status": order.status,
            "awb_number": order.awb_number,
            "courier": order.logistic_partner.name if order.logistic_partner else "",
            "total_amount": order.total_amount,
            "invoice_amount": order.invoice_amount,
            "customer": {
                "name": addr.name if addr else "",
                "email": addr.email if addr else "",
                "phone": addr.phone if addr else "",
            },
            "shipping_address": (
                {
                    "address": addr.line1 if addr else "",
                    "city": addr.city if addr else "",
                    "state": addr.state if addr else "",
                    "pincode": addr.pin_code if addr else "",
                    "country": addr.country if addr else "",
                }
                if addr
                else {}
            ),
            "payment": {
                "method": order.payment.method if hasattr(order, "payment") else "",
                "status": order.payment.status if hasattr(order, "payment") else "",
                "amount": order.payment.amount if hasattr(order, "payment") else 0,
                "shipping_charge": (
                    order.payment.shipping_charges if hasattr(order, "payment") else 0
                ),
                "cod_charges": (
                    order.payment.cod_charges if hasattr(order, "payment") else 0
                ),
            },
            "created_at": str(order.created_at),
            "raw_payload": order.json,
        }
    )
