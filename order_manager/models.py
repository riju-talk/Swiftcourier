from datetime import timedelta
import logging
import os
import uuid
import barcode

from barcode.writer import ImageWriter
from django.utils.text import slugify
from django.utils.timezone import now
from django.core.files import File
from django.db import models, transaction, IntegrityError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth import get_user_model
from account.models import Courier, MyModel, Notification, RateCard
from django.db.models import QuerySet, Sum, Q, CharField
from django.db.models.functions import Coalesce, Cast
from django.utils import timezone
from django.utils.timezone import localdate

from utils.payout_date import get_next_payout_date

from django.conf import settings
from wallet.models import Transaction


logger = logging.getLogger("my-logger")
User = get_user_model()


class BulkOrderFile(MyModel):
    """
    Model to store bulk order upload files.
    """

    file = models.FileField(upload_to="bulk_order_files/%Y/%m/%d/")


class Hub(MyModel):
    """
    Represents a pickup hub with contact and address details.
    """

    name = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=100, blank=True)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=6, default=000000)
    country = models.CharField(max_length=50, default="India")
    gstin = models.CharField(max_length=17, blank=True, help_text="GSTIN (Tax ID)")
    phone = models.CharField(max_length=10)
    alt_phone = models.CharField(max_length=10, blank=True)
    email = models.EmailField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="hubs")
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    json = models.JSONField(default=dict)

    class Meta(MyModel.Meta):
        # a hub name only needs to be unique *within* a merchant's account -
        # two merchants may both have a "Main Warehouse".
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="uniq_hub_name_per_user"
            )
        ]

    def __str__(self):
        return self.name

    @staticmethod
    def get_primary(user):
        """Returns the primary hub for a user, or the first active hub if no primary is set."""
        hubs = Hub.objects.filter(user=user, is_active=True)
        primary_hub = hubs.filter(is_primary=True).first()
        if primary_hub is not None:
            return primary_hub

        return hubs.first()

    def get_hub_address(self):
        """Returns the full address of the hub as a formatted string."""
        return f"{self.address_line1}, {self.address_line2}, {self.city}, {self.state}, {self.pin_code}, {self.country}"

    def to_address(self) -> "Address":
        """Convert the hub to Address's attribute format"""
        return {
            "name": self.contact_person,
            "user": self.user.id,
            "label": "",
            "line1": self.address_line1,
            "line2": self.address_line2,
            "landmark": "Office",
            "company_name": "SwiftCourier",
            "city": self.city,
            "state": self.state,
            "pin_code": self.pin_code,
            "country": self.country,
            "phone": self.phone,
            "alt_phone": self.alt_phone,
            "email": self.email,
        }


class Address(MyModel):
    """
    Stores user addresses for shipping and billing, including optional fields.
    """

    name = models.CharField(max_length=100, default="")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="order_addresses"
    )
    label = models.CharField(
        max_length=50, blank=True, help_text="e.g., Home, Office", default=""
    )
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, default="")
    landmark = models.CharField(
        max_length=255, blank=True, help_text="Nearby place or landmark", default=""
    )
    company_name = models.CharField(
        max_length=255, blank=True, help_text="Company or Organization", default=""
    )
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=6, default="000000")
    country = models.CharField(max_length=50, default="India")
    phone = models.CharField(max_length=10, blank=True)
    alt_phone = models.CharField(
        max_length=10, default="", help_text="Alternate phone number"
    )
    email = models.EmailField(blank=True, help_text="Consignee email", default="")

    def __str__(self):
        return f"{self.user.email} - {self.label or 'Address'}"

    def get_full_address(self):
        return f"{self.line1}, {self.line2}, {self.landmark}, {self.city}, {self.state}, {self.pin_code}, {self.country}"


class Product(MyModel):
    """
    Represents a product with SKU, dimensions, weight, and pricing.
    """

    sku = models.CharField(max_length=200)
    name = models.TextField()
    hsn_code = models.CharField(max_length=50, default="")
    description = models.TextField(blank=True)

    # Use floats for weights, and positive integers for dimensions in cm
    weight_kg = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(9999.999)]
    )
    length_cm = models.PositiveIntegerField(validators=[MaxValueValidator(99999999)])
    width_cm = models.PositiveIntegerField(validators=[MaxValueValidator(99999999)])
    height_cm = models.PositiveIntegerField(validators=[MaxValueValidator(99999999)])

    # Use float for pricing
    price = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(9999999999.99)]
    )
    stock = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.sku} - {self.name}"


class Order(MyModel):
    """
    Represents a customer order with status, addresses, and related details.
    """

    ORDER_MAPPING = {
        "ready_to_ship": "Ready To Ship",
        "processing": "Processing",
        "pending_pickup": "Pending Pickup",
        "in_transit": "In Transit",
        "out_for_delivery": "Out For Delivery",
        "delivered": "Delivered",
        "cancelled": "Cancelled",
        "lost": "Lost",
        "damaged": "Damaged",
        "exception": "Exception",
        "ndr": "NDR",
        "rto": "RTO",
        "rto_pending_pickup": "RTO Pending Pickup",
        "rto_in_transit": "RTO In Trasnit",
        "rto_out_for_delivery": "RTO Out For Delivery",
        "rto_delivered": "RTO Delivered",
        "rto_cancelled": "RTO Cancelled",
        "rto_lost": "RTO Lost",
        "rto_damaged": "RTO Damaged",
    }
    ORDER_STATUS = list(ORDER_MAPPING.items())
    ALL_ORDER_STATUS = [i for i in ORDER_MAPPING]

    CHANNEL_CHOICES = [
        ("shopify", "Shopify"),
        ("amazon", "Amazon"),
        ("woocommerce", "Woocommerce"),
        ("bulk_upload", "Bulk Upload"),
        ("custom", "Custom"),
    ]

    bulk_order_file = models.ForeignKey(
        to=BulkOrderFile,
        on_delete=models.SET_NULL,
        null=True,
        default=None,
    )

    # TODO: fix it
    logistic_partner = models.ForeignKey(
        to=Courier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="orders",
        help_text="Logistic partner for this order",
    )
    awb_number = models.CharField(max_length=30, help_text="AWB number")
    route_code = models.CharField(max_length=30, default="")
    order_number = models.CharField(
        max_length=150, help_text="Order number", default="0"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    shipping_address = models.OneToOneField(
        Address, on_delete=models.SET_NULL, null=True, related_name="order"
    )
    billing_address = models.ForeignKey(
        Address, on_delete=models.SET_NULL, null=True, related_name="billing_orders"
    )
    channel = models.CharField(
        max_length=25,
        help_text="Order source (e.g., Shopify, Website)",
        default="custom",
        choices=CHANNEL_CHOICES,
    )
    status = models.CharField(
        max_length=50, choices=ORDER_STATUS, default="ready_to_ship"
    )

    # Switch total_amount to float
    # its also selling price
    # its not shipping charge
    total_amount = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(9999999999.99)],
    )
    invoice_amount = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(9999999999.99)],
    )

    placed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, help_text="Additional instructions from user")
    hub = models.ForeignKey(
        Hub, on_delete=models.PROTECT, related_name="orders", null=True, default=None
    )
    order_date = models.DateTimeField(auto_now_add=True)
    barcode = models.ImageField(
        upload_to="barcode/%Y/%m/%d/",
        default="default/barcode.png",
        null=True,
        blank=True,
    )
    cod_remittance = models.ForeignKey(
        "CODRemittance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="orders",
    )
    shopify_fulfillment_id = models.CharField(
        max_length=100,
        default="",
        blank=True,
        help_text="Shopify fulfillment ID after we push tracking back",
    )

    _is_locked = models.BooleanField(
        default=False, help_text="If true, order cannot be punch"
    )
    """
    {
        "awb_number": {
            "cancelled_at": "2023-10-10T10:10:10Z",
            "courier": "XpressBees",
            "refund_amount": 50.0,
        }
    }
    """
    cancel_data = models.JSONField(default=dict, help_text="Cancellation details")
    """Example:
    {
        "rate_card_details": {
            "id": 67,
            "mode": "surface",
            "base_weight": "0.5",
            "addl_weight": "0.5",
            "zone": "rest_of_india",
        },
        etc...
    }
    """
    json = models.JSONField(default=dict)

    class Meta(MyModel.Meta):
        indexes = [
            # dashboard / shipment-tab counts + list filtering
            models.Index(fields=["user", "status", "-created_at"], name="order_user_status_created"),
            models.Index(fields=["user", "-created_at"], name="order_user_created"),
            models.Index(fields=["status"], name="order_status"),
            # search / lookups
            models.Index(fields=["awb_number"], name="order_awb"),
            models.Index(fields=["order_number"], name="order_number_idx"),
        ]

    # def lock_order(self):
    #     """Deprecated (Build processing tab)
    #     Lock the order to prevent punching."""
    #     self._is_locked = True
    #     self.save(update_fields=["_is_locked"])

    # def unlock_order(self):
    #     """Deprecated (Build processing tab)
    #     Unlock the order to allow punching."""
    #     self._is_locked = False
    #     self.save(update_fields=["_is_locked"])

    # @property
    # def is_locked(self) -> bool:
    #     """Returns whether the order is locked."""
    #     return self._is_locked

    @staticmethod
    def send_to_processing(
        order_ids: list[int], user: User
    ) -> tuple[list[int], list[int]]:
        """Set order status to processing (for processing tab)"""
        qs = Order.objects.filter(id__in=order_ids, user=user)

        ready_ids = []
        failed_ids = []

        for oid, status in qs.values_list("id", "status"):
            if status == "ready_to_ship":
                ready_ids.append(oid)
            else:
                failed_ids.append(oid)

        if ready_ids:
            # bump updated_at too - .update() skips auto_now, and reclaim_stuck_processing
            # needs an accurate "entered processing at" timestamp.
            Order.objects.filter(id__in=ready_ids).update(
                status="processing", updated_at=now()
            )

        return ready_ids, failed_ids

    @staticmethod
    def reclaim_stuck_processing(user, older_than_minutes: int = 30) -> int:
        """Move this user's orders that have been genuinely stranded in
        `processing` back to `ready_to_ship` (the async ship task died / never
        ran, or the worker is down). Returns how many were reclaimed.

        An order is only reclaimed if it has been in `processing` past the
        cutoff AND has NOT been shipped or charged yet - i.e. it has no
        `awb_number` and no SUCCESS shipping-charge transaction. That guard stops
        this (which runs on every load of the Processing list) from yanking
        orders out from under a slow-but-alive worker mid-ship.
        """
        from wallet.models import Transaction

        cutoff = now() - timedelta(minutes=older_than_minutes)
        candidates = Order.objects.filter(
            user=user, status="processing", updated_at__lt=cutoff
        ).exclude(awb_number__gt="")  # awb set -> carrier already booked it

        charged_order_ids = set(
            Transaction.objects.filter(
                user=user, desc="shipping_charges", status="SUCCESS",
                merchant_transaction_id__startswith=f"{user.id}_shipping_charges_",
            ).values_list("merchant_transaction_id", flat=True)
        )

        ids = []
        for oid in candidates.values_list("id", flat=True):
            key = f"{user.id}_shipping_charges_{oid}_"
            if any(m.startswith(key) for m in charged_order_ids):
                continue  # already paid for -> mid-ship, leave it
            ids.append(oid)

        if not ids:
            return 0
        Order.objects.filter(id__in=ids).update(
            status="ready_to_ship", updated_at=now()
        )
        try:
            Notification.objects.create(
                user=user,
                category="warning",
                msg=f"{len(ids)} order(s) were stuck processing and have been "
                "returned to Ready to Ship. Please try shipping them again.",
            )
        except Exception:
            pass
        return len(ids)

    @classmethod
    def total_cod_collected(cls, user):
        """Calculate total COD collected for a user's orders."""
        return cls.objects.filter(
            user=user, status="delivered", payment__method="cod"
        ).aggregate(total_cod=Coalesce(Sum("total_amount"), 0.0))["total_cod"]

    def save(self, *args, **kwargs):
        """
        Override save() to generate a Code128 barcode image for AWB.
        Uses font_size=0 to hide any text under the bars.
        & sets last_order_at on the user if this is a new order.
        """
        if not self.id:
            self.user.last_order_at = now()
            self.user.save(update_fields=["last_order_at"])

        temp_file_path = None
        my_order = Order.objects.filter(pk=self.pk).first()
        if my_order:
            old_status = my_order.status

        if kwargs.get("generate_barcode") or (
            my_order and self.awb_number != my_order.awb_number
        ):
            try:
                # ---- DELETE OLD BARCODE IF EXISTS ----
                if self.pk:
                    old = Order.objects.filter(pk=self.pk).first()
                    if old and old.barcode:
                        old.barcode.delete(save=False)

                # generate_barcode now returns the path to the file it wrote
                # full_path = self.generate_barcode(self.awb_number)
                temp_file_path = self.generate_barcode(self.awb_number)

                # Open the file and attach it to the ImageField without immediately saving the model
                with open(temp_file_path, "rb") as f:
                    django_file = File(f)
                    # The 'name' we give here is the upload-to path + filename,
                    # e.g. "barcodes/barcode_xpressbees_14344951668118.png"
                    filename_only = os.path.basename(temp_file_path)
                    self.barcode.save(filename_only, django_file, save=False)

            except Exception as e:
                # If barcode is required and generation failed, raise
                if not self.barcode:
                    raise ValueError(f"Barcode generation failed: {e}")

            finally:
                # ---- DELETE TEMP FILE SAFELY ----
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                    except Exception:
                        pass  # don't fail save() if cleanup fails

        if "generate_barcode" in kwargs:
            del kwargs["generate_barcode"]

        # NOTE: the RTO wallet debit that used to live here has moved into
        # update_status() (see _charge_rto_charges). Order.save() must not have
        # financial side effects - it bypasses the wallet service's locking and
        # idempotency, and fires on every save() including unrelated writes.

        super().save(*args, **kwargs)

    def generate_barcode(self, data) -> str:
        """
        Generate a Code128 barcode image file under settings.TMP_DIR.
        Returns the full path (string) to the PNG file that was created.
        """
        options = {
            "module_width": 0.3,  # Width of each bar module
            "module_height": 7.0,  # Height of each bar
            "quiet_zone": 1.0,  # Margin on each side
            "font_size": 0,  # Hide the numeric text
            "text_distance": 0.0,  # Text-to-barcode gap
            "background": "white",
            "foreground": "black",
            "write_text": False,
        }

        code128 = barcode.get_barcode_class("code128")
        barcode_instance = code128(data, writer=ImageWriter())

        # Build a slugified filename in our temp directory
        file_slug = slugify(f"barcode_{self.logistic_partner}_{data}")
        # If you want a .png extension explicitly:
        filename_without_ext = str(file_slug)
        tmp_dir = settings.TMP_DIR  # Path object or string pointing to a temp folder
        output_path = os.path.join(tmp_dir, filename_without_ext)

        # The save() method on a python-barcode writer returns the actual filename
        # including extension (e.g. "/tmp/barcode_xpressbees_12345.png").
        saved_filename = barcode_instance.save(output_path, options=options)

        return saved_filename

    def __str__(self):
        return f"Order {self.id} ({self.user.email})"

    def calculate_total(self):
        """Calculates and updates the total amount for the order based on its items."""
        total = sum(item.total_price for item in self.items.all())
        self.total_amount = total
        self.save(update_fields=["total_amount"])
        return self.total_amount

    def calculate_gst_amount(self) -> float:
        """Calculates GST amount based on the total amount and GST rate from settings."""
        self.calculate_total()
        return self.total_amount * settings.GST_ON_SHIPMENT

    def invoice_summary(self) -> dict:
        """A reconciled breakdown for the customer order-details / invoice view.

        ``items_subtotal`` is the sum of the line items; charges and discount come
        off ``payment`` (all default 0 when there is no Payment row). ``tax_amount``
        is computed from ``tax_percent`` against the items subtotal. ``grand_total``
        stays the authoritative ``order.total_amount`` the merchant declared - if
        the parts don't add up to it (a manual override) ``adjustment`` carries the
        difference so the column still balances.
        """
        pay = getattr(self, "payment", None)

        def _f(name):
            return float(getattr(pay, name, 0) or 0) if pay else 0.0

        items_subtotal = round(
            sum(float(i.total_price or 0) for i in self.items.all()), 2
        )
        tax_percent = _f("tax_percent")
        tax_amount = round(items_subtotal * tax_percent / 100, 2)
        shipping = _f("shipping_charges")
        cod = _f("cod_charges")
        gift_wrap = _f("gift_wrap_charges")
        other = _f("other_charges")
        discount = _f("discount")
        grand_total = round(float(self.total_amount or 0), 2)

        computed = round(
            items_subtotal + tax_amount + shipping + cod + gift_wrap + other - discount,
            2,
        )
        adjustment = round(grand_total - computed, 2)

        return {
            "items_subtotal": items_subtotal,
            "tax_percent": tax_percent,
            "tax_amount": tax_amount,
            "shipping_charges": shipping,
            "cod_charges": cod,
            "gift_wrap_charges": gift_wrap,
            "other_charges": other,
            "discount": discount,
            "adjustment": adjustment,
            "grand_total": grand_total,
        }

    def get_order_id(self):
        """Returns a formatted order ID string (SwiftCourier reference)."""
        return f"SC{self.id}"

    def get_order_id_for_aggregator(self):
        """Returns the order ID that will be used for downstream aggregator processing."""
        if self.order_number:
            return self.order_number
        else:
            return self.get_order_id()

    def update_status(
        self, new_status: str, tracking_history: list[dict] | None = None
    ) -> bool:
        """Updates the order status, handling barcode deletion if needed.
        Parameters:
            new_status: New Status
            tracking_history: List of dictionary
        """
        if new_status not in self.ALL_ORDER_STATUS:
            return False

        previous_status = self.status

        # A carrier that re-sends the same status must be a cheap no-op, not a
        # re-run of every side effect (extra saves, duplicate notifications).
        if new_status == previous_status:
            return True

        # ---- if order is completed or cancelled, remove barcode ----
        if new_status in ["delivered", "cancelled", "rto_delivered"]:
            if self.barcode:
                self.barcode.delete(save=False)  # deletes from S3 + DB
                self.barcode = None

        # Shipment is a reverse OneToOne - a webhook can fire for an order that
        # never got one. Touch its timestamps only if it exists; never let a
        # missing Shipment 500 the status transition.
        shipment = getattr(self, "shipment", None)
        if shipment is not None:
            stamp = {
                "pending_pickup": "booked_at",
                "in_transit": "shipped_at",
                "delivered": "delivered_at",
                "rto": "rto_at",
                "rto_delivered": "rto_delivered_at",
            }.get(new_status)
            if stamp and getattr(shipment, stamp, None) is None:
                setattr(shipment, stamp, now())
            if tracking_history is not None and isinstance(tracking_history, list):
                shipment.tracking_history = tracking_history
            shipment.save()
        elif tracking_history is not None:
            logger.warning("Order #%s: status webhook but no Shipment row", self.id)

        if new_status == "cancelled":
            try:
                awb = str(self.awb_number)
                if awb:
                    self.cancel_data[awb] = {
                        "cancelled_at": now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "courier": (
                            f"{self.logistic_partner.name} ({self.logistic_partner.abbreviation})"
                            if self.logistic_partner
                            else "N/A"
                        ),
                        "refund_amount": (
                            float(self.payment.shipping_charges)
                            if getattr(self, "payment", None)
                            else 0.0
                        ),
                        "done_by": "update_status_method",
                    }
            except Exception:
                logger.exception(f"Error updating cancel_data for Order #{self.id}: ")

        self.status = new_status
        self.updated_at = now()  # update_fields skips auto_now
        self.save(update_fields=["status", "barcode", "cancel_data", "updated_at"])

        # RTO leg entered -> charge RTO freight once (moved out of Order.save,
        # §9.2.1). Deterministic idempotency key so a replayed webhook / retried
        # task cannot double-debit.
        if "rto" not in previous_status and new_status.startswith("rto"):
            self._charge_rto_charges()

        if previous_status != new_status:
            self._dispatch_status_notifications(new_status, previous_status)

        return True

    def _dispatch_status_notifications(self, new_status: str, old_status: str) -> None:
        """Queue customer WhatsApp/SMS notifications for this status change.

        No-op unless settings.CUSTOMER_NOTIFICATIONS_ENABLED is on. Even then the
        tasks themselves are gated per-merchant (WhatsAppSettings.enabled /
        SMSSettings.enabled, both default False) and skip silently when the
        status has no configured template. Never raises - a broker outage or an
        import error must not break the status transition.
        """
        from django.conf import settings

        if not getattr(settings, "CUSTOMER_NOTIFICATIONS_ENABLED", False):
            return
        try:
            from whatsapp_integration.tasks import send_whatsapp_notification
            from SMS_integration.tasks import send_sms_notification
        except Exception:
            logger.exception("Order #%s: notification tasks unavailable", self.id)
            return
        for task in (send_whatsapp_notification, send_sms_notification):
            try:
                task.delay(self.id, new_status, old_status)
            except Exception:
                logger.exception(
                    "Order #%s: could not queue %s", self.id, getattr(task, "name", task)
                )

    def _charge_rto_charges(self) -> None:
        """Debit the RTO freight for this order, exactly once.

        Called from update_status on the transition into an rto* state. Uses a
        deterministic merchant_transaction_id so duplicate transitions are
        no-ops at the DB unique-constraint level rather than double-debits.
        """
        try:
            rto_charges = (self.payment.price_breakup or {}).get("rto_charges", 0)
        except Exception:
            logger.exception(f"Order #{self.id}: could not read rto_charges")
            return
        if not rto_charges:
            return

        # merchant_transaction_id is stored as str(user.id) + this value and is
        # unique. Cheap pre-check for the common replayed-webhook case, plus a
        # try/except to close the race - wrapped in its own atomic() so a failed
        # INSERT never poisons an outer transaction if a caller adds one later.
        mtid = f"{self.user_id}_rto_charges_order_{self.id}"
        if Transaction.objects.filter(merchant_transaction_id=mtid).exists():
            logger.info(f"Order #{self.id}: RTO charge already posted, skipping")
            return
        try:
            with transaction.atomic():
                trxn = Transaction.create_transaction(
                    self.user,
                    merchant_txn_id=f"_rto_charges_order_{self.id}",
                    amount_rs=rto_charges,
                    desc="rto_charges",
                    transaction_type="debit",
                )
        except IntegrityError:
            logger.info(f"Order #{self.id}: RTO charge already posted, skipping")
            return

        if not trxn.debit(forcefully=True, awb_number=self.awb_number):
            Notification.objects.create(
                user=self.user,
                msg=f"Failed to debit ₹{rto_charges} for RTO charges",
                category="error",
            )

    def charge_shipping(self, amount: float) -> "Transaction | None":
        """Debit shipping charges for this order exactly once *per AWB*.

        The merchant_transaction_id is deterministic (order id + current AWB), so
        a retried ship task or a double-clicked "Ship" button reuses the same
        transaction instead of debiting twice. A re-ship after cancellation gets
        a fresh AWB, so it legitimately charges again.

        Returns the SUCCESS Transaction, or None if the debit could not go
        through (caller should roll the order back to ready_to_ship). The wallet
        move itself is row-locked inside Transaction.debit -> User.debit.
        """
        amount = float(amount or 0)
        if amount <= 0:
            # 0 = nothing to charge; < 0 = a broken rate card / price_breakup -
            # never let that credit the wallet.
            if amount < 0:
                logger.error(
                    "Order #%s: refusing negative shipping charge %s", self.id, amount
                )
            return None

        key = f"_shipping_charges_{self.id}_{self.awb_number or 'noawb'}"
        mtid = f"{self.user_id}{key}"

        trxn = Transaction.objects.filter(merchant_transaction_id=mtid).first()
        if trxn is None:
            try:
                with transaction.atomic():
                    trxn = Transaction.create_transaction(
                        self.user,
                        merchant_txn_id=key,
                        amount_rs=amount,
                        desc="shipping_charges",
                        transaction_type="debit",
                    )
            except IntegrityError:
                trxn = Transaction.objects.filter(merchant_transaction_id=mtid).first()

        if trxn is None:
            logger.error(f"Order #{self.id}: could not create shipping-charge txn")
            return None
        if trxn.status == "SUCCESS":
            return trxn  # already charged for this AWB - idempotent no-op

        if trxn.debit(awb_number=self.awb_number):
            return trxn
        return None

    def refund_shipping(
        self, amount: float | None = None, desc: str = "cancelled_order"
    ) -> "Transaction | None":
        """Credit the shipping charge back for this order exactly once *per AWB*.

        Mirror of charge_shipping: the merchant_transaction_id is deterministic
        (order id + current AWB), so a double-clicked "Cancel" button or a
        retried cancel task refunds only once. A re-ship + re-cancel gets a
        fresh AWB and refunds again, correctly.

        `amount` defaults to exactly what `charge_shipping` debited for the
        current AWB (found via its deterministic transaction id), falling back to
        `payment.shipping_charges` only if no charge is on record. Returns the
        SUCCESS Transaction, or None if there was nothing to credit back.
        """
        if amount is None:
            charge_mtid = (
                f"{self.user_id}_shipping_charges_{self.id}_"
                f"{self.awb_number or 'noawb'}"
            )
            charged = (
                Transaction.objects.filter(
                    merchant_transaction_id=charge_mtid,
                    status="SUCCESS",
                    transaction_type="debit",
                )
                .values_list("amount", flat=True)
                .first()
            )
            if charged is not None:
                amount = charged
            else:
                amount = getattr(self.payment, "shipping_charges", 0) or 0
        amount = float(amount or 0)
        if amount <= 0:
            if amount < 0:
                logger.error(
                    "Order #%s: refusing negative refund %s", self.id, amount
                )
            return None

        key = f"_cancel_refund_{self.id}_{self.awb_number or 'noawb'}"
        mtid = f"{self.user_id}{key}"

        trxn = Transaction.objects.filter(merchant_transaction_id=mtid).first()
        if trxn is None:
            try:
                with transaction.atomic():
                    trxn = Transaction.create_transaction(
                        self.user,
                        merchant_txn_id=key,
                        amount_rs=amount,
                        desc=desc,
                        transaction_type="credit",
                    )
            except IntegrityError:
                trxn = Transaction.objects.filter(
                    merchant_transaction_id=mtid
                ).first()

        if trxn is None:
            logger.error(f"Order #{self.id}: could not create refund txn")
            return None
        if trxn.status == "SUCCESS":
            return trxn  # already refunded for this AWB - idempotent no-op

        if trxn.credit(awb_number=self.awb_number):
            return trxn
        return None

    @staticmethod
    def delete_non_required_barcode() -> int:
        """Delete barcode files for orders that are delivered or cancelled."""
        orders = Order.objects.filter(status__in=["delivered", "cancelled"])
        count = 0

        for o in orders:
            if o.barcode:
                o.barcode.delete(save=False)  # deletes from S3 + DB
                o.barcode = None
                o.save()

                count += 1

        return count

    @staticmethod
    def delete_expired_bulk_order_files():
        """
        Deletes BulkOrderFile records (and physical files) older than
        BULK_ORDER_FILE_EXPIRATION_DAYS and clears their references from Orders.
        """
        expiration_days = settings.BULK_ORDER_FILE_EXPIRATION_DAYS
        expiration_time = now() - timedelta(days=expiration_days)

        expired_orders = (
            Order.objects.filter(
                bulk_order_file__created_at__lt=expiration_time,
                bulk_order_file__isnull=False,
            )
            .select_related("bulk_order_file")
            .iterator()
        )

        deleted_files = 0
        failed = 0

        for order in expired_orders:
            bulk_file = order.bulk_order_file
            if not bulk_file:
                continue

            try:
                with transaction.atomic():
                    file_path = getattr(bulk_file.file, "path", None)

                    # Delete physical file if exists
                    if file_path and os.path.exists(file_path):
                        os.remove(file_path)
                        logger.debug(f"Removed file: {file_path}")

                    # Delete the BulkOrderFile record
                    bulk_file.delete()

                    # Clear FK on Order
                    order.bulk_order_file = None
                    order.save(update_fields=["bulk_order_file"])

                    deleted_files += 1
                    logger.info(f"Deleted bulk order file for Order #{order.id}")

            except Exception as e:
                failed += 1
                logger.error(f"Error deleting bulk file for Order #{order.id}: {e}")

        logger.info(f"Cleanup complete: {deleted_files} deleted, {failed} failed.")


class OrderItem(MyModel):
    """
    Represents an item within an order, linking to the product and its pricing details.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.OneToOneField(
        Product, on_delete=models.PROTECT, related_name="order_item"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.FloatField(validators=[MinValueValidator(0.0)])
    total_price = models.FloatField(validators=[MinValueValidator(0.0)])
    sku_code = models.CharField(
        max_length=50, default="", help_text="Optional SKU override"
    )

    def save(self, *args, **kwargs):
        # Auto-calculate prices
        self.unit_price = self.product.price
        # self.total_price = round(self.unit_price * self.quantity, 2)
        super().save(*args, **kwargs)
        # Update order total
        self.order.calculate_total()

    def __str__(self):
        return f"{self.quantity} x {self.product.sku} for Order {self.order.id}"


class Shipment(MyModel):
    """
    Tracks shipment details for an order, including status and package dimensions.
    """

    SHIPMENT_STATUS = [
        ("booked", "Booked"),
        ("in_transit", "In Transit"),
        ("out_for_delivery", "Out for Delivery"),
        ("delivered", "Delivered"),
        ("failed", "Delivery Failed"),
    ]
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="shipment"
    )
    courier = models.ForeignKey(Courier, on_delete=models.SET_NULL, null=True)
    tracking_number = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=SHIPMENT_STATUS, default="booked")

    booked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    rto_at = models.DateTimeField(null=True, blank=True)
    rto_delivered_at = models.DateTimeField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)

    # Package dimensions
    package_weight_kg = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(9999.999)],
    )
    volumetric_weight_kg = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(9999.999)],
    )
    package_length_cm = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(99999999)]
    )
    package_width_cm = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(99999999)]
    )
    package_height_cm = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(99999999)]
    )

    hub = models.ForeignKey(
        Hub, on_delete=models.SET_NULL, null=True, blank=True, related_name="shipments"
    )
    is_insured = models.BooleanField(default=False)

    """List of tracking histories. Like:
    {
        "status": "delivered",
        "timestamp": "2026-01-21 15:52:59",
        "location": "NBM/NBM, Navi Mumbai, MAHARASHTRA",
        "description": "Shipment Delivered"
    }
    """
    tracking_history = models.JSONField(default=list)

    def __str__(self):
        return f"Shipment {self.tracking_number} ({self.status})"


class Payment(MyModel):
    """
    Stores payment details for an order, including method, status, and charges.
    """

    PAYMENT_METHODS = [
        ("prepaid", "Prepaid"),
        ("cod", "COD"),
        ("wallet", "Wallet"),
        ("online", "Online Gateway"),
    ]
    ALL_PAYMENT_METHODS = [i for i, _ in PAYMENT_METHODS]

    PAYMENT_STATUS = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]
    ALL_PAYMENT_STATUS = [i for i, _ in PAYMENT_STATUS]

    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="payment"
    )
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="prepaid")
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default="pending")
    transaction_id = models.CharField(max_length=100, blank=True)

    # total amount paid (in Rs)
    amount = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(9999999999.99)]
    )
    shipping_charges = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0)]
    )
    cod_charges = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    cod_collectable_amount = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0)]
    )
    discount = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    gift_wrap_charges = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0)]
    )
    other_charges = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    tax_percent = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    """
    {
        "base_charge": <base_charge>,
        "additional_charges": <additional_charges>,
        "cod_charge": <cod_charge>,
        "gst_amount": <gst_amount>,
        "rto_base_charge": <rto_base_charge>,
        "rto_additional_charge": <rto_additional_charge>,
        "rto_gst_amount": <rto_gst_amount>,
        "rto_charges": <rto_charges>,
    }
    """
    price_breakup = models.JSONField(default=dict)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.transaction_id or self.id} for Order {self.order.id}"


class CODRemittance(MyModel):
    """
    Tracks Cash on Delivery (COD) remittances to users.
    Each user can have only ONE remittance per payout date.
    """

    REMITTANCE_STATUS = [
        ("paid", "Paid"),
        ("adjusted", "Adjusted"),
        ("pending", "Pending"),
        ("failed", "Failed"),
        ("partial_paid", "Partial Paid"),
        ("hold", "Hold"),
        ("other", "Other"),
    ]

    # ---- FIELDS ----
    _user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="cod_remittances"
    )

    _status = models.CharField(
        max_length=50, choices=REMITTANCE_STATUS, default="pending"
    )

    _generated_cod = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(9999999999.99)]
    )
    _freight_deduction = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0)]
    )
    _early_cod_charge_percentage = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    _early_cod_charge = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0)]
    )
    _remittance_amount = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(9999999999.99)]
    )
    # _orders = models.
    # its the file of excel which contains orders details for which cod remittance is done
    _file = models.FileField(
        upload_to="cod_remittances/%Y/%m/%d/", blank=True, null=True, default=None
    )

    _amount_paid = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    _order_count = models.PositiveIntegerField(default=0)

    _utr_no = models.CharField(max_length=100, blank=True)

    _payout_date = models.DateField(null=True, blank=True, db_index=True)
    _remarks = models.TextField(blank=True)

    # ---- UNIQUE CONSTRAINT ----
    class Meta:
        unique_together = ("_user", "_payout_date")
        ordering = ["-_payout_date", "-id"]

    def __str__(self):
        return f"COD Remittance {self.id} | {self._user.email} | {self._status}"

    def get_file(self):
        """
        Returns the URL of the order's file if it exists.
        """
        return self._file.url if self._file else None

    def get_awb_numbers(self):
        """
        Returns a list of AWB numbers associated with this remittance's orders.
        """
        return list(
            Order.objects.filter(cod_remittance=self)
            .distinct()
            .values_list("awb_number", flat=True)
        )

    @staticmethod
    def remitted_till_date(user):
        """
        Returns the total remitted amount for a user till date.
        """
        total = (
            CODRemittance.objects.filter(_user=user, _status="paid").aggregate(
                total=Sum("_remittance_amount")
            )["total"]
            or 0.0
        )
        return total

    @staticmethod
    def last_remittance(user):
        """
        Returns the last remittance amount for a user.
        """
        last_remittance = (
            CODRemittance.objects.filter(_user=user, _status="paid")
            .order_by("-_payout_date")
            .first()
        )
        if last_remittance:
            return last_remittance._remittance_amount
        return 0.0

    # =====================================================================
    # FETCH COD DELIVERED ORDERS FOR A GIVEN DATE
    # =====================================================================
    @staticmethod
    def get_user_cod_orders_for_day(user, date=None):
        """
        Returns COD delivered orders for a user on a specific date.
        If date is None, uses the current local date."""
        orders = Order.objects.filter(
            user=user,
            payment__method="cod",
            status="delivered",
            cod_remittance__isnull=True,  # only consider orders not already linked to a remittance
        )
        if date is not None:
            orders = orders.filter(shipment__delivered_at__date__lte=date)

        return orders

    @classmethod
    def get_for_a_user(cls, user):
        """
        Returns all COD remittances for a specific user.
        """
        return cls.objects.filter(_user=user)

    # =====================================================================
    # GENERATE REMITTANCE FOR USER
    # =====================================================================
    @classmethod
    def generate_for_user(cls, user, date, logger=None):
        """
        Generates COD remittance for a user for orders delivered on a specific date.
        If logger is provided, logs detailed steps.
        """

        orders = cls.get_user_cod_orders_for_day(user, date)

        if logger is not None:
            logger.debug(
                f"Generating COD remittance for user {user.email}. Found {orders.count()} eligible orders."
            )

        if not orders.exists():
            if logger is not None:
                logger.debug(f"No eligible COD orders for user {user.email}. Skipping.")
            return None

        # ---- CALCULATIONS ----
        generated_cod = orders.aggregate(total=Sum("total_amount"))["total"] or 0.0

        remittance_amount = round(generated_cod, 2)
        order_count = orders.count()

        # ---- GET NEXT PAYOUT DATE ----
        payout_date = get_next_payout_date(localdate())

        if logger is not None:
            logger.debug(
                f"Calculated remittance for user {user.email}: "
                f"Generated COD={generated_cod}, "
                f"Remittance Amount={remittance_amount}, "
                f"Order Count={order_count}, "
                f"Payout Date={payout_date}."
            )

        # ---- CHECK IF REMITTANCE ALREADY EXISTS ----
        cod_remittance_qs = cls.objects.filter(
            _user=user,
            _payout_date=payout_date,
        )

        if cod_remittance_qs.exists():
            cod_remittance_obj = cod_remittance_qs.first()

            if logger is not None:
                logger.debug(
                    f"COD Remittance already exists for user {user.email} "
                    f"on payout date {payout_date}. Updating existing record."
                )

            cod_remittance_obj._generated_cod += generated_cod
            cod_remittance_obj._remittance_amount += remittance_amount
            cod_remittance_obj._order_count += order_count
            cod_remittance_obj.save()

            for order in orders:
                order.cod_remittance = cod_remittance_obj
                order.save(update_fields=["cod_remittance"])

            return cod_remittance_obj

        if logger is not None:
            logger.debug(
                f"Creating new COD Remittance for user {user.email} "
                f"on payout date {payout_date}."
            )

        # ---- CREATE REMITTANCE ----
        cod_remittance_obj = cls.objects.create(
            _user=user,
            _status="pending",
            _generated_cod=generated_cod,
            _remittance_amount=remittance_amount,
            _amount_paid=0,
            _order_count=order_count,
            _payout_date=payout_date,
            _remarks="",
        )
        for order in orders:
            order.cod_remittance = cod_remittance_obj
            order.save(update_fields=["cod_remittance"])

        return cod_remittance_obj

    # =====================================================================
    # GENERATE FOR ALL USERS
    # =====================================================================
    @classmethod
    def generate_for_all_users(cls, date, logger=None):
        """
        Generates COD remittances for all users for orders delivered on a specific date.
        If logger is provided, logs detailed steps.
        """
        summary = {"created": 0, "skipped": 0}
        users = User.objects.filter(is_active=True, role=User.USER)
        if logger is not None:
            logger.debug(f"Generating COD remittance for {users.count()} users.")

        for user in users:
            try:
                obj = cls.generate_for_user(user, date=date, logger=logger)
                summary["created" if obj else "skipped"] += 1
            except Exception as e:
                if logger is not None:
                    logger.error(
                        f"Error generating COD remittance for user {user.email}: {e}"
                    )
                summary["skipped"] += 1

        if logger is not None:
            logger.debug(f"COD Remittance generation summary: {summary}.")

        return summary

    @classmethod
    def get_user_remittance_dashboard(cls, user, query: str | None = None):
        """
        Optimized dashboard summary + table data for COD remittance page
        Supports search filtering.
        """
        total_cod_collected = Order.total_cod_collected(user)

        remittances = cls.get_for_a_user(user).only(
            "id",
            "_payout_date",
            "_generated_cod",
            "_freight_deduction",
            "_early_cod_charge_percentage",
            "_early_cod_charge",
            "_remittance_amount",
            "_amount_paid",
            "_order_count",
            "_utr_no",
            "_remarks",
            "_status",
        )

        # ======================================================
        # SEARCH FILTER
        # ======================================================
        if query:
            query = query.strip()

            remittances = (
                remittances.annotate(
                    generated_cod_str=Cast("_generated_cod", CharField()),
                    freight_str=Cast("_freight_deduction", CharField()),
                    early_cod_per_str=Cast("_early_cod_charge_percentage", CharField()),
                    remittance_str=Cast("_remittance_amount", CharField()),
                )
                .filter(
                    Q(orders__awb_number__icontains=query)
                    | Q(generated_cod_str__icontains=query)
                    | Q(freight_str__icontains=query)
                    | Q(early_cod_per_str__icontains=query)
                    | Q(remittance_str__icontains=query)
                    | Q(_utr_no__icontains=query)
                    | Q(_remarks__icontains=query)
                    | Q(_status__icontains=query)
                )
                .distinct()
            )

        # ------------------------------------------------
        # DB Level Aggregations
        # ------------------------------------------------
        aggregates = remittances.aggregate(
            total_freight_adjusted=Coalesce(
                Sum("_freight_deduction", filter=Q(_status__in=["paid", "adjusted"])),
                0.0,
            ),
            remitted_till_date=Coalesce(
                Sum("_amount_paid", filter=Q(_status__in=["paid", "adjusted"])),
                0.0,
            ),
        )

        # ------------------------------------------------
        # Last Remittance
        # ------------------------------------------------
        last_paid = (
            remittances.filter(_status__in=["paid", "adjusted"])
            .order_by("-created_at")
            .values_list("_amount_paid", flat=True)
            .first()
            or 0.0
        )

        summary = {
            "remitted_till_date": round(aggregates["remitted_till_date"], 2),
            "last_remittance": round(last_paid, 2),
            "next_remittance_expected": 0.0,
            "total_remittance_due": 0,
            "total_cod_collected": round(total_cod_collected, 2),
            "total_freight_adjusted": round(aggregates["total_freight_adjusted"], 2),
            "cod_remittances": [],
        }

        summary["total_remittance_due"] = round(
            (
                total_cod_collected
                - summary["remitted_till_date"]
                - summary["total_freight_adjusted"]
            ),
            2,
        )

        if summary["total_remittance_due"] < 0:
            summary["total_remittance_due"] = 0

        # ------------------------------------------------
        # Table Data + Next Expected Calculation
        # ------------------------------------------------
        next_expected_set = False

        for remittance in remittances:
            if not next_expected_set and remittance._status not in ["paid", "adjusted"]:
                summary["next_remittance_expected"] = (
                    remittance._generated_cod - remittance._freight_deduction
                )
                next_expected_set = True

            summary["cod_remittances"].append(
                {
                    "id": remittance.id,
                    "payout_date": remittance._payout_date,
                    "payout_amount": round(float(remittance._generated_cod or 0), 2),
                    "generated_cod": round(float(remittance._generated_cod or 0), 2),
                    "frieght_deduction": round(
                        float(remittance._freight_deduction or 0), 2
                    ),
                    "early_cod_charges_percentage": round(
                        float(remittance._early_cod_charge_percentage or 0), 2
                    ),
                    "early_cod_charges": round(
                        float(remittance._early_cod_charge or 0), 2
                    ),
                    "remittance_amount": round(
                        float(remittance._remittance_amount or 0), 2
                    ),
                    "amount_paid": round(float(remittance._amount_paid or 0), 2),
                    "order_count": remittance._order_count,
                    "utr": remittance._utr_no,
                    "remarks": remittance._remarks,
                    "status": remittance.get__status_display(),
                }
            )

        return summary


class CarrierWebhookEvent(MyModel):
    """Raw inbound carrier webhook, persisted before any business processing.

    This is the single reliable source for debugging and replaying a carrier
    integration after the fact (PRD 6.7.3, 7.4.1). It is deliberately separate
    from any outgoing merchant-webhook records - one table never serves both.
    """

    PROCESSING_CHOICES = [
        ("received", "Received"),
        ("ignored", "Ignored"),
        ("processed", "Processed"),
        ("failed", "Failed"),
        ("duplicate", "Duplicate"),
    ]

    carrier = models.CharField(max_length=40, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    request_path = models.CharField(max_length=255, default="")
    request_method = models.CharField(max_length=10, default="POST")
    headers = models.JSONField(default=dict, help_text="Redacted request headers")
    raw_body = models.TextField(default="", help_text="Raw request body (redacted)")
    body_sha256 = models.CharField(max_length=64, default="", db_index=True)
    parsed_payload = models.JSONField(null=True, blank=True, default=None)
    external_event_id = models.CharField(max_length=120, default="", blank=True, db_index=True)
    awb_number = models.CharField(max_length=40, default="", blank=True, db_index=True)
    external_status = models.CharField(max_length=80, default="", blank=True)
    mapped_status = models.CharField(max_length=40, default="", blank=True)
    # None  = no signature mechanism / not checked (log-only rollout)
    # True  = signature verified
    # False = signature verification failed
    signature_valid = models.BooleanField(null=True, default=None)
    processing_status = models.CharField(
        max_length=12, choices=PROCESSING_CHOICES, default="received", db_index=True
    )
    processing_attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(default="", blank=True)
    order = models.ForeignKey(
        "Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="webhook_events"
    )
    correlation_id = models.CharField(max_length=64, default="", db_index=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["carrier", "received_at"])]

    def __str__(self):
        return f"{self.carrier} webhook @ {self.received_at:%Y-%m-%d %H:%M:%S} ({self.processing_status})"
