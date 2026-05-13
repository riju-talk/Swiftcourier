# shopify_integration/services/shopify_client.py

import logging

import requests
from django.conf import settings

logger = logging.getLogger("my-logger")


class ShopifyAPIError(Exception):
    """Raised when Shopify Admin API returns a non-2xx response."""
    pass


class ShopifyClient:
    """
    Wraps all outbound Shopify Admin REST API calls.

    One instance per merchant — constructed with shop_domain + access_token.
    All methods raise ShopifyAPIError on non-2xx responses.

    Usage:
        client = ShopifyClient(user.shopify_shop_domain, user.shopify_access_token)
        order  = client.get_order("5123456789")
    """

    def __init__(self, shop_domain: str, access_token: str):
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.api_version = settings.SHOPIFY["API_VERSION"]
        self.base_url = f"https://{shop_domain}/admin/api/{self.api_version}"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    # ── PRIVATE HTTP HELPERS ──────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url  = f"{self.base_url}{endpoint}"
        resp = requests.get(url, headers=self.headers, params=params, timeout=15)
        if not resp.ok:
            raise ShopifyAPIError(
                f"GET {endpoint} failed [{resp.status_code}]: {resp.text}"
            )
        return resp.json()

    def _post(self, endpoint: str, payload: dict) -> dict:
        url  = f"{self.base_url}{endpoint}"
        resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
        if not resp.ok:
            raise ShopifyAPIError(
                f"POST {endpoint} failed [{resp.status_code}]: {resp.text}"
            )
        return resp.json()

    def _delete(self, endpoint: str) -> bool:
        url  = f"{self.base_url}{endpoint}"
        resp = requests.delete(url, headers=self.headers, timeout=15)
        return resp.status_code == 200

    # ── ORDERS ────────────────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> dict:
        """
        Fetch a single Shopify order by its ID.

        Args:
            order_id: Shopify order ID (numeric string).

        Returns:
            Order dict from Shopify API.
        """
        return self._get(f"/orders/{order_id}.json").get("order", {})

    def get_orders(self, limit: int = 50) -> list:
        """
        Fetch unfulfilled open orders from Shopify.

        Args:
            limit: Max number of orders to return (default 50, max 250).

        Returns:
            List of order dicts.
        """
        data = self._get("/orders.json", params={
            "status":             "open",
            "fulfillment_status": "unfulfilled",
            "limit":              limit,
        })
        return data.get("orders", [])

    # ── FULFILLMENTS ──────────────────────────────────────────────────────────

    def get_fulfillment_orders(self, order_id: str) -> list:
        """
        Get fulfillment orders for a Shopify order.

        Required to get fulfillment_order_id before creating a fulfillment
        (Shopify API 2022-07+).

        Args:
            order_id: Shopify order ID string.

        Returns:
            List of fulfillment_order dicts.
        """
        data = self._get(f"/orders/{order_id}/fulfillment_orders.json")
        return data.get("fulfillment_orders", [])

    def create_fulfillment(
        self,
        order_id: str,
        tracking_number: str,
        courier_name: str,
        tracking_url: str = "",
        notify_customer: bool = True,
    ) -> dict:
        """
        Push AWB + tracking info back to Shopify as a fulfillment.

        Uses the new fulfillments API (Shopify 2022-07+):
            Step 1 — Get fulfillment_order_id from /fulfillment_orders
            Step 2 — POST to /fulfillments.json

        Args:
            order_id:        Shopify order ID string.
            tracking_number: AWB / tracking number string.
            courier_name:    Courier display name.
            tracking_url:    Full tracking URL (optional).
            notify_customer: Whether Shopify sends tracking email (default True).

        Returns:
            Shopify API response dict with 'fulfillment' key.

        Raises:
            ShopifyAPIError if no fulfillment orders found or API fails.
        """
        fulfillment_orders = self.get_fulfillment_orders(order_id)
        if not fulfillment_orders:
            raise ShopifyAPIError(
                f"No fulfillment orders found for Shopify order {order_id}."
            )

        fulfillment_order_id = fulfillment_orders[0]["id"]

        payload = {
            "fulfillment": {
                "line_items_by_fulfillment_order": [
                    {"fulfillment_order_id": fulfillment_order_id}
                ],
                "tracking_info": {
                    "number":  tracking_number,
                    "company": courier_name,
                    "url":     tracking_url,
                },
                "notify_customer": notify_customer,
            }
        }
        return self._post("/fulfillments.json", payload)

    def cancel_fulfillment(self, fulfillment_id: str) -> dict:
        """
        Cancel a fulfillment on Shopify by fulfillment ID.

        Args:
            fulfillment_id: Shopify fulfillment ID string.

        Returns:
            Shopify API response dict.
        """
        return self._post(f"/fulfillments/{fulfillment_id}/cancel.json", {})

    # ── WEBHOOKS ──────────────────────────────────────────────────────────────

    def get_webhooks(self) -> list:
        """
        List all webhooks currently registered for this shop.

        Returns:
            List of webhook dicts.
        """
        return self._get("/webhooks.json").get("webhooks", [])

    def register_webhook(self, topic: str, address: str) -> dict:
        """
        Register a single webhook on Shopify.

        Args:
            topic:   Shopify webhook topic (e.g. 'orders/create').
            address: Your server URL that will receive the webhook.

        Returns:
            Shopify API response dict with 'webhook' key.
        """
        payload = {
            "webhook": {
                "topic":   topic,
                "address": address,
                "format":  "json",
            }
        }
        return self._post("/webhooks.json", payload)

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Delete a registered webhook by ID.

        Args:
            webhook_id: Shopify webhook ID string.

        Returns:
            True if deleted, False otherwise.
        """
        return self._delete(f"/webhooks/{webhook_id}.json")

    def register_all_webhooks(self, app_base_url: str) -> list:
        """
        Register all webhooks required for the courier aggregator integration.

        Topics registered:
            orders/create    → /shopify/webhooks/orders/created/
            orders/updated   → /shopify/webhooks/orders/updated/
            orders/cancelled → /shopify/webhooks/orders/cancelled/
            orders/paid      → /shopify/webhooks/orders/paid/
            app/uninstalled  → /shopify/auth/uninstall/

        Call this once per merchant during the OAuth callback.

        Args:
            app_base_url: Your app's public base URL (e.g. https://yourdomain.com).

        Returns:
            List of result dicts with keys: topic, status, result/error.
        """
        required = [
            ("orders/create",    f"{app_base_url}/shopify/webhooks/orders/created/"),
            ("orders/updated",   f"{app_base_url}/shopify/webhooks/orders/updated/"),
            ("orders/cancelled", f"{app_base_url}/shopify/webhooks/orders/cancelled/"),
            ("orders/paid",      f"{app_base_url}/shopify/webhooks/orders/paid/"),
            ("app/uninstalled",  f"{app_base_url}/shopify/auth/uninstall/"),
        ]

        results = []
        for topic, address in required:
            try:
                logger.info(f"[ShopifyClient] Webhook registering...")
                result = self.register_webhook(topic, address)
                results.append({"topic": topic, "status": "ok", "result": result})
            except ShopifyAPIError as e:
                logger.exception(f"Got error while registering webhook of topic: {topic}")
                results.append({"topic": topic, "status": "failed", "error": str(e)})

        return results

    # ── LOCATIONS ─────────────────────────────────────────────────────────────

    def get_locations(self) -> list:
        """
        Get all locations configured for this Shopify shop.

        Returns:
            List of location dicts.
        """
        return self._get("/locations.json").get("locations", [])

    def get_primary_location_id(self) -> str | None:
        """
        Return the ID of the first active location for this shop.

        Returns:
            Location ID string, or None if no active location found.
        """
        for loc in self.get_locations():
            if loc.get("active"):
                return str(loc["id"])
        return None