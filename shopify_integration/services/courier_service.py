# shopify_integration/services/courier_service.py

import importlib
import logging

from account.models import Courier

logger = logging.getLogger("my-logger")


class CourierServiceError(Exception):
    """Raised when courier booking, cancellation, or tracking fails."""

    pass


class CourierService:
    """
    Bridge between the Shopify integration and your courier aggregator.

    Uses the integration_path field on each Courier model to dynamically
    load the correct courier module — the same pattern used elsewhere in
    your system (e.g. xpressbees_integration.xpressbees).

    Usage:
        service = CourierService(user)
        result  = service.create_shipment(payload)

    Each courier module must expose:
        create_shipment(api_key, payload, user) → dict
        cancel_shipment(api_key, awb)           → dict
        get_tracking(api_key, awb)              → dict
    """

    def __init__(self, user):
        self.user = user

    # ── PRIVATE HELPERS ───────────────────────────────────────────────────────

    def _get_preferred_courier(self) -> Courier:
        """
        Return the user's top-preference active courier.

        Priority:
            1. First entry in CourierPreferenceSequence (ordered by position).
            2. First courier from the user's rate cards.

        Raises:
            CourierServiceError if no courier is available.
        """
        preferred = self.user.get_courier_preference()
        if preferred:
            return preferred[0]

        available = self.user.get_available_couriers()
        if available:
            return available[0]

        raise CourierServiceError(
            f"No courier available for user {self.user.email}. "
            "Please configure courier preferences or rate cards."
        )

    def _load_courier_module(self, courier: Courier):
        """
        Dynamically import the courier integration module using the
        integration_path stored on the Courier model instance.

        e.g. 'xpressbees_integration.xpressbees'

        Args:
            courier: Courier instance with a valid integration_path.

        Returns:
            Imported Python module.

        Raises:
            CourierServiceError if module cannot be imported.
        """
        try:
            return importlib.import_module(courier.integration_path)
        except ImportError as e:
            raise CourierServiceError(
                f"Could not load courier module '{courier.integration_path}': {e}"
            )

    # ── PUBLIC METHODS ────────────────────────────────────────────────────────

    def create_shipment(self, payload: dict) -> dict:
        """
        Book a shipment with the user's preferred courier.

        Args:
            payload: Dict built in webhook_processor.py with keys:
                order_id, pickup (dict), delivery (dict),
                weight_kg, is_cod, cod_amount, invoice_amount, channel

        Returns:
            Dict with keys:
                awb           – AWB / tracking number string
                courier       – Courier model instance
                tracking_url  – Full tracking URL string
                charge        – Shipping charge float (INR)
                cod_charge    – COD charge float (INR)
                price_breakup – Dict with itemised charge breakdown

        Raises:
            CourierServiceError if booking fails.
        """
        courier = self._get_preferred_courier()
        module = self._load_courier_module(courier)

        try:
            result = module.create_shipment(
                api_key=courier.api_key,
                payload=payload,
                user=self.user,
            )
            # Attach courier instance and tracking URL to result
            result["courier"] = courier
            result["tracking_url"] = courier.get_tracking_url(result.get("awb", ""))
            logger.info(
                f"[CourierService] Shipment booked | "
                f"AWB={result.get('awb')} | Courier={courier.name}"
            )
            return result

        except Exception as e:
            raise CourierServiceError(
                f"Shipment booking failed with courier '{courier.name}': {e}"
            )

    def cancel_shipment(self, awb: str) -> dict:
        """
        Cancel a booked shipment by AWB number.

        Args:
            awb: AWB / tracking number string.

        Returns:
            Dict with at minimum:
                refund_amount – Float amount to refund to wallet (INR)

        Raises:
            CourierServiceError if cancellation fails.
        """
        courier = self._get_preferred_courier()
        module = self._load_courier_module(courier)

        try:
            result = module.cancel_shipment(
                api_key=courier.api_key,
                awb=awb,
            )
            logger.info(f"[CourierService] Shipment cancelled | AWB={awb}")
            return result

        except Exception as e:
            raise CourierServiceError(
                f"Shipment cancellation failed for AWB '{awb}': {e}"
            )

    def get_tracking(self, awb: str) -> dict:
        """
        Fetch live tracking status for a shipment by AWB.

        Args:
            awb: AWB / tracking number string.

        Returns:
            Dict with at minimum:
                status  – Normalized status string matching Order.ORDER_MAPPING keys
                history – List of tracking event dicts (for Shipment.tracking_history)

        Raises:
            CourierServiceError if tracking fetch fails.
        """
        courier = self._get_preferred_courier()
        module = self._load_courier_module(courier)

        try:
            return module.get_tracking(
                api_key=courier.api_key,
                awb=awb,
            )
        except Exception as e:
            raise CourierServiceError(f"Tracking fetch failed for AWB '{awb}': {e}")
