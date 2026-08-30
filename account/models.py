import logging
from decimal import Decimal
from typing import Union
from django.contrib.auth.models import AbstractUser

from .money import to_money

from .managers import UserManager
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction as db_transaction
from django.conf import settings
from django_resized import ResizedImageField  # type: ignore
from django.utils.timezone import now
from datetime import timedelta
import uuid


logger = logging.getLogger("my-logger")


# helper function
def get_default_rate() -> dict:
    return {
        "forward_base": 0.0,
        "forward_additional": 0.0,
        "rto_base": 0.0,
        "rto_additional": 0.0,
    }


class MyModel(models.Model):
    """An abstract base class model that provides self-updating 'created' and 'modified' fields."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class Courier(MyModel):
    """
    Courier model representing a shipping/delivery service provider.
    This model stores information about courier services integrated into the system,
    including their configuration, contact details, and tracking capabilities.
    Attributes:
        available_modes (JSONField): List of available shipping modes/services offered by the courier.
        name (str): Display name of the courier service (max 50 characters).
        abbreviation (str): Unique abbreviation code for the courier (max 40 characters).
        integration_path (str): Python module path for the courier's integration implementation.
            Default: "xpressbees_integration.xpressbees"
        icon (ResizedImageField): Courier logo/icon image (100x100px), uploaded to 'courier_icons/'.
        _base_tracking_url (str): Base URL template for tracking shipments with {tracking_id} placeholder.
        contact_email (str): Email address for courier support contact.
        contact_phone (str): Phone number for courier support contact (max 10 digits).
        website (str): Official website URL of the courier.
        api_key (str): API key for courier integration (max 255 characters).
        active (bool): Whether the courier is currently active/available (default: True).
    Methods:
        get_couriers_by_ids(ids): Retrieve active courier instances by their IDs.
        get_tracking_url(tracking_id): Generate a complete tracking URL for a shipment.
        set_tracking_url(value): Update the base tracking URL template.
    """

    available_modes = models.JSONField(default=list)

    name = models.CharField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=40, default="", unique=True)
    integration_path = models.CharField(
        max_length=255, default="xpressbees_integration.xpressbees"
    )  # e.g., "xpressbees_integration.xpressbees"
    icon = ResizedImageField(
        size=[100, 100], upload_to="courier_icons/", default="default/no_image.png"
    )
    _base_tracking_url = models.URLField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Tracking URL (use {tracking_id} as placeholder)",
        help_text="Example: https://www.xpressbees.com/shipment/tracking?awbNo={tracking_id}",
    )
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=10, blank=True)
    website = models.URLField(blank=True)
    api_key = models.CharField(max_length=255, blank=True, help_text="For integrations")
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    @staticmethod
    def get_couriers_by_ids(ids: list[int]):
        """
        Retrieve active couriers by their IDs.

        Fetches a list of Courier objects from the database that match the provided IDs
        and have an active status. Couriers that don't exist or are inactive are skipped,
        and a warning is logged for each missing or inactive courier.

        Args:
            ids (list[int]): A list of courier IDs to retrieve.

        Returns:
            list[Courier]: A list of active Courier objects matching the provided IDs.
                           The list may be smaller than the input if some couriers
                           don't exist or are inactive.

        Note:
            - Silently skips non-existent or inactive couriers with a warning log.
            - Each failed lookup is logged as a warning for debugging purposes.
        """
        couriers = []
        for id in ids:
            try:
                courier = Courier.objects.get(id=id, active=True)
                couriers.append(courier)
            except Courier.DoesNotExist:
                logger.warning(f"Courier with id {id} does not exist or is inactive.")
        return couriers

    def get_tracking_url(self, tracking_id: str) -> str:
        """
        Generate a tracking URL by replacing the tracking ID placeholder.

        Args:
            tracking_id (str): The tracking identifier to be inserted into the URL.

        Returns:
            str: The complete tracking URL with the tracking ID substituted.
        """
        return self._base_tracking_url.replace("{tracking_id}", tracking_id)

    def set_tracking_url(self, value: str):
        """
        Set the base tracking URL for the account.

        Args:
            value (str): The base tracking URL to be set.
        """
        self._base_tracking_url = value


class RateCard(MyModel):
    """RateCard model for managing shipping rates and courier information.
    This model stores shipping rate cards for different couriers and users.
    It uses a JSONField to store complex hierarchical rate information organized by:
    - Mode (surface, air, ship)
    - Weight brackets
    - Additional weight
    - Zone (within_city, within_state, metro_to_metro, rest_of_india, ne_jk)
    - Flow (forward, rto)
    - Rate type (base, additional, cod_charges, cod_percentage)
    Attributes:
        courier (ForeignKey): Reference to the Courier associated with this rate card.
        user (ForeignKey): Reference to the User who owns this rate card.
        data (JSONField): Hierarchical dictionary containing rate information.
    Methods:
        get_couriers_available_for_user(): Returns a dictionary of couriers available for the user.
        get_rate(): Fetches a specific shipping rate from the data structure.
        set_rate(): Sets a specific shipping rate in the data structure.
        get_rate_by_data(): Fetches rate using a formatted string with hyphen-separated parameters.
        set_rate_by_data(): Sets multiple rates from a dictionary of formatted strings.
        get_cod_percentage(): Fetches the COD percentage for given parameters.
        get_available_weights(): Returns list of available weight brackets for a mode.
        get_additional_weight(): Returns the additional weight for a given weight bracket.
        get_available_modes(): Returns list of available shipping modes.
        calculate_cod_charges(): Calculates COD charges based on flat rate vs percentage.
        calculate_price(): Placeholder method for price calculation logic.
    """

    courier = models.ForeignKey(
        to=Courier,
        related_name="rate_cards",
        verbose_name="Courier Name (ex: Xpressbees)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        to="User",
        related_name="rate_cards",
        verbose_name="User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    """Example:
    {
        "air": {
            # use it in str due to float's precision issues
            "0.5": {
                "within_city": {
                    "forward": {
                        "base": 50.0,
                        "additional": 20.0,
                        "cod_charges": 20.0,
                        "cod_percentage": 20.0,
                    }
                }
            }
        }
    }
    """
    data = models.JSONField(default=dict)

    def get_couriers_available_for_user(self) -> dict[int, Courier]:
        """
        Retrieve all couriers available for the user based on their rate cards.
        Returns:
            dict[int, Courier]: A dictionary mapping courier IDs to Courier objects.
                               The keys are courier IDs and the values are the corresponding
                               Courier instances that have active rate cards for this user.
        """

        couriers = {}
        rate_cards = RateCard.objects.filter(user=self.user)
        for rate_card in rate_cards:
            couriers[rate_card.courier.id] = rate_card.courier

        return couriers

    def get_rates(self, mode: str):
        return self.data

    def get_rate(
        self,
        mode: str,
        weight: str,
        additional_weight: str,
        zone: str,
        flow: str,
        kind: str,
    ) -> float:
        """
        Fetches the shipping rate from the appropriate JSONField.

        Args:
            mode: "surface" or "air"
            zone: "within_city", "within_state", "metro_to_metro", "rest_of_india", "ne_jk"
            flow: "forward" or "rto"
            kind: "base", "additional", "cod_charges", "cod_percentage"

        Returns:
            float: The shipping rate
            OR
            KeyError: if the rate is not found.
        """
        mode = mode.lower()
        zone = zone.lower()
        flow = flow.lower()
        kind = kind.lower()
        # check if weight and additional_weight are valid floats
        float(weight)
        float(additional_weight)

        output = self.data[mode][weight][additional_weight][zone][flow][kind]
        return float(output)

    def set_rate(
        self,
        mode: str,
        weight: str,
        additional_weight: str,
        zone: str,
        flow: str,
        kind: str,
        value: float,
    ):
        """
        Set a shipping rate with the specified parameters.
        Args:
            mode (str): The shipping mode. Must be one of: 'surface', 'air', 'ship'.
            weight (str): The package weight as a string. Must be convertible to float.
            additional_weight (str): The additional weight as a string. Must be convertible to float.
            zone (str): The delivery zone. Must be one of: 'within_city', 'within_state',
                        'metro_to_metro', 'rest_of_india', 'ne_jk'.
            flow (str): The shipment flow type. Must be one of: 'forward', 'rto'.
            kind (str): The rate type. Must be one of: 'base', 'additional', 'cod_charges', 'cod_percentage'.
            value (float): The rate value to be set.
        Raises:
            ValueError: If mode, zone, flow, or kind parameters are not valid values.
            ValueError: If weight or additional_weight cannot be converted to float.
        Returns:
            None
        """
        if mode not in {"surface", "air", "ship"}:
            return ValueError(f"Invalid mode: {mode}")

        # check if weight is a valid float
        weight = str(float(weight))
        additional_weight = str(float(additional_weight))

        if zone not in {
            "within_city",
            "within_state",
            "metro_to_metro",
            "rest_of_india",
            "ne_jk",
        }:
            raise ValueError(f"Invalid zone: {zone}")

        if flow not in {"forward", "rto"}:
            raise ValueError(f"Invalid flow: {flow}")

        if kind not in {"base", "additional", "cod_charges", "cod_percentage"}:
            raise ValueError(f"Invalid kind: {kind}")

        self.data.setdefault(mode, {}).setdefault(weight, {}).setdefault(
            additional_weight, {}
        ).setdefault(zone, {}).setdefault(flow, {})[kind] = float(value)

    def get_rate_by_data(self, data: str) -> float:
        """
        Calculate shipping rate from a formatted data string.
        Args:
            data (str): A hyphen-separated string containing exactly 5 elements in the format:
                       "mode-weight-additional_weight-zone-flow-kind"
        Returns:
            float: The calculated shipping rate based on the provided parameters.
        Raises:
            ValueError: If the data string does not contain exactly 5 hyphen-separated elements.
        Example:
            >>> rate = get_rate_by_data("standard-5-0-zone1-express-parcel")
            >>> print(rate)
            25.50
        """
        data = data.split("-")
        if len(data) != 5:
            raise ValueError(
                "Data must contain exactly 5 elements: mode, weight, zone, flow, kind"
            )

        mode, weight, additional_weight, zone, flow, kind = data
        return self.get_rate(mode, weight, additional_weight, zone, flow, kind)

    def set_rate_by_data(self, data: dict):
        """
        Set shipping rates from a dictionary of rate data.

        Parses a dictionary where each key contains hyphen-separated rate parameters
        and the value is the rate to be set. Each key is split into its components
        (mode, weight, additional_weight, zone, flow, kind) and used to set the
        corresponding rate.

        Args:
            data (dict): A dictionary where keys are formatted as strings with
                         hyphen-separated values: "mode-weight-additional_weight-zone-flow-kind"
                         and values are the rates to be set for each combination.

        Returns:
            None

        Side Effects:
            Calls set_rate() for each key-value pair and saves the model instance
            after each rate is set.
        """
        for key, value in data.items():
            mode, weight, additional_weight, zone, flow, kind = key.split("-")
            self.set_rate(mode, weight, additional_weight, zone, flow, kind, value)
            self.save()

    def get_cod_percentage(
        self,
        mode: str,
        weight: str,
        additional_weight: str,
        zone: str = "within_city",
        flow: str = "forward",
    ) -> float:
        """
        Get the COD (Cash on Delivery) percentage for a shipment.

        Args:
            mode (str): The shipping mode/carrier type.
            weight (str): The base weight of the shipment.
            additional_weight (str): Any additional weight charges.
            zone (str, optional): The delivery zone. Defaults to "within_city".
            flow (str, optional): The shipment flow type. Defaults to "forward".

        Returns:
            float: The COD percentage applicable for the given parameters.
        """
        return self.get_rate(
            mode, weight, additional_weight, zone, flow, "cod_percentage"
        )

    def get_available_weights(self, mode: str = "surface") -> list[str]:
        """
        Retrieve available weights for a given shipping mode.
        Args:
            mode (str): The shipping mode to get weights for (e.g., "surface", "air").
                       Defaults to "surface". If an empty string or falsy value is provided,
                       all weights across all modes will be returned.
        Returns:
            list[str]: A list of available weight options for the specified mode,
                       or all weights across all modes if mode is falsy.
        Example:
            >>> get_available_weights("surface")
            ['1kg', '5kg', '10kg']
            >>> get_available_weights("")
            ['1kg', '5kg', '10kg', '2kg', '8kg']
        """
        weights = []

        if mode:
            for weight in self.data.get(mode, []):
                weights.append(weight)
        else:
            for mode in self.data:
                for weight in self.data.get(mode, []):
                    weights.append(weight)

        return weights

    def get_additional_weight(
        self,
        mode: str,
        weight: str,
    ) -> str | Exception:
        """
        Retrieve the additional weight value for a given mode and weight.
        Args:
            mode (str): The mode type to search for (case-insensitive).
            weight (str): The weight category to look up.
        Returns:
            str | Exception: The additional weight value as a string if found,
                             otherwise raises a ValueError.
        Raises:
            ValueError: If the specified weight is not found in the given mode.
                        Includes available weights in the error message.
        Example:
            >>> result = get_additional_weight("surface", "5")
            >>> print(result)
            "1"
        """
        value = "0.0"
        mode = mode.lower()

        if mode not in self.data:
            return value

        for key, data in self.data[mode].items():
            logger.debug(
                f"Checking key: {key} for weight: {weight}for Mode: {mode}\n{self.data[mode].items()}"
            )
            if key == weight:
                try:
                    value = list(data.keys())[0]
                    break
                except IndexError:
                    pass
        else:
            raise ValueError(
                f"Additional Weight not found for mode '{mode}', and weight '{weight}'. Available weights: {self}"
            )

        return value

    def calculate_price(self):
        pass

    def get_available_modes(self) -> list[str]:
        """
        Get the list of available modes.

        Returns a list of all keys from the data dictionary, representing
        the available modes that can be accessed.

        Returns:
            list[str]: A list of available mode names.
        """
        return list(self.data.keys())

    def calculate_cod_charges(
        self,
        mode: str,
        weight: str,
        additional_weight: str,
        zone: str,
        flow: str,
        selling_price: float,
    ) -> float:
        """
        Calculate the Cash on Delivery (COD) charges based on the shipping parameters.
        Determines the COD charge by comparing a fixed rate-based charge with a
        percentage-based charge and returns the higher of the two values.
        Args:
            mode (str): The shipping mode/service type.
            weight (str): The base weight of the shipment.
            additional_weight (str): Any additional weight surcharge applicable.
            zone (str): The delivery zone/region.
            flow (str): The shipment flow type (e.g., forward, return).
            selling_price (float): The selling price of the shipment, used to calculate
                                  percentage-based COD charges.
        Returns:
            float: The calculated COD charge rounded to 2 decimal places.
        """
        cod_charge: float = 0.0

        cod_charges_rate = self.get_rate(
            mode, weight, additional_weight, zone, flow, "cod_charges"
        )
        cod_percentage_charge = (
            self.get_rate(mode, weight, additional_weight, zone, flow, "cod_percentage")
            / 100  # Convert percentage to decimal
        ) * selling_price

        if cod_charges_rate > cod_percentage_charge:
            cod_charge = cod_charges_rate
        else:
            cod_charge = cod_percentage_charge

        return round(cod_charge, 2)


class LabelSetting(MyModel):
    """
    Model for managing label display settings and customization options.

    This model stores configuration preferences for shipping labels, allowing users to
    control which information and elements are displayed on generated labels.

    Attributes:
        show_logo (BooleanField): Whether to display the company logo on the label. Defaults to False.
        logo (ImageField): The logo image file to display on the label. Optional field accepting image uploads.
        show_support_info (BooleanField): Whether to display support contact information. Defaults to False.
        support_email (CharField): Support email address to display on the label. Max length 30 characters.
        support_phone (CharField): Support phone number to display on the label. Max length 10 characters.
        show_customer_mobile (BooleanField): Whether to display the customer's mobile number. Defaults to True.
        show_pickup_address (BooleanField): Whether to display the pickup address. Defaults to True.
        show_product (BooleanField): Whether to display product information. Defaults to False.
        show_total_amount (BooleanField): Whether to display the total shipment amount. Defaults to True.
        show_weight (BooleanField): Whether to display the package weight. Defaults to True.
        show_dimension (BooleanField): Whether to display the package dimensions. Defaults to True.
        show_discount (BooleanField): Whether to display the discount column. Defaults to False.
        show_powered_by (BooleanField): Whether to display the "powered by" attribution. Defaults to True.
    """

    new_label = models.BooleanField(default=True)
    show_logo = models.BooleanField(default=False)
    logo = models.ImageField(upload_to="label/logo/%Y/%m/%d/", null=True, blank=True)
    show_support_info = models.BooleanField(default=False)
    support_email = models.CharField(max_length=30, default="")
    support_phone = models.CharField(max_length=10, default="")
    show_customer_mobile = models.BooleanField(default=True)
    show_pickup_address = models.BooleanField(default=True)
    show_product = models.BooleanField(default=False)
    show_total_amount = models.BooleanField(default=True)
    show_weight = models.BooleanField(default=True)
    show_dimension = models.BooleanField(default=True)
    show_discount = models.BooleanField(default=False)
    show_powered_by = models.BooleanField(default=False)
    label_page_size = models.CharField(
        max_length=10,
        choices=(
            ("a4", "A4"),
            ("a4_single", "A4 (single label)"),
            ("4x6", "4x6"),
            ("3x5", "3x5"),
        ),
        default="4x6",
    )


class User(AbstractUser):
    """
    User model representing a custom user account with extended functionality.
    This model extends Django's AbstractUser and provides:
    - Role-based access control (USER, ADMIN, SUPER_ADMIN)
    - Account status tracking (active, sleeping, dead)
    - KYC (Know Your Customer) verification support
    - Financial account details (bank information, balance management)
    - Address and contact information
    - Document storage (GST certificate, PAN card, Aadhaar card, etc.)
    - Wallet balance management with transaction logging
    - Courier preference management and rate card associations
    - Label settings for shipment customization
    Attributes:
        AVAILABLE_ROLES (tuple): List of valid user roles
        ROLE_CHOICES (tuple): Choices for role field display
        STATUS (tuple): Choices for user account status
        USERNAME_FIELD (str): Uses email as the unique identifier instead of username
    Key Features:
        - Uses email as the primary identifier (USERNAME_FIELD)
        - Automatic status updates based on last order date
        - Balance management with credit/debit methods
        - KYC agreement tracking
        - Courier preference ordering
        - Default admin user assignment
        - Maximum wallet balance validation
        - Negative balance allowance configuration
    Meta:
        ordering: Orders users by creation date in descending order
    """

    username = None
    first_name = None
    last_name = None
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    AVAILABLE_ROLES = (USER, ADMIN, SUPER_ADMIN)
    ROLE_CHOICES = (
        (USER, "User"),
        (ADMIN, "Admin"),
        (SUPER_ADMIN, "Super Admin"),
    )
    STATUS = (
        ("dead", "Dead"),
        ("active", "Active"),
        ("sleeping", "Sleeping"),
    )

    # roles
    role = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default="user",
        verbose_name="User Role",
        choices=ROLE_CHOICES,
    )

    # see status property for more info
    _status = models.CharField(
        max_length=20,
        default=STATUS[0][0],
        choices=STATUS,
        verbose_name="Account Status",
    )

    # details
    email = models.EmailField(
        max_length=255,
        unique=True,
        blank=False,
        verbose_name="Email Address",
    )
    full_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="",
        verbose_name="Full Name (e.g., Anuj Tiwari)",
    )
    contact_no = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Contact Number (with country code)",
    )
    company_name = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="",
        verbose_name="Company Name (if applicable)",
    )
    gstin = models.CharField(
        max_length=17,
        blank=True,
        null=True,
        default="",
        verbose_name="GSTIN (Tax ID)",
    )

    # financial details
    bank_name = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="",
        verbose_name="Bank Account Name",
    )
    bank_account_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default="",
        verbose_name="Bank Account Number",
    )
    bank_account_ifsc = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default="",
        verbose_name="Bank Account IFSC Code",
    )
    bank_account_type = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default="saving",
        verbose_name="Bank Account Type",
        choices=(
            ("saving", "Saving"),
            ("current", "Current"),
        ),
    )

    # address details
    address = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="",
        verbose_name="Full Address",
    )
    pin_code = models.CharField(
        max_length=6,
        blank=True,
        null=True,
        default="",
        verbose_name="PIN Code",
    )
    city = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="",
        verbose_name="City",
    )
    state = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="",
        verbose_name="State",
    )
    country = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default="india",
        verbose_name="Country (default: India)",
    )

    # documents details
    gst_certificate = ResizedImageField(
        upload_to="documents/gst_certificate/",
        blank=True,
        null=True,
        default=None,
        verbose_name="GST Certificate/Company Incorporated Document ",
    )

    photo = ResizedImageField(
        upload_to="documents/profile_photo/",
        default="default/user_logo.png",
        verbose_name="Profile picture, photo, or selfie",
    )

    pan_card = ResizedImageField(
        upload_to="documents/pan_card/",
        blank=True,
        null=True,
        default=None,
        verbose_name="PAN Card/Driving License",
    )

    aadhaar_card = ResizedImageField(
        upload_to="documents/aadhaar_card/",
        blank=True,
        null=True,
        default=None,
        verbose_name="Aadhaar Card/Passport/Voter ID Card",
    )

    cancel_cheque = ResizedImageField(
        upload_to="documents/cancel_cheque/",
        blank=True,
        null=True,
        default=None,
        verbose_name="Cancelled Cheque",
    )

    # account details
    # Please dont cut money directly from user balance, use Transaction model instead
    # to create a transaction and then call credit() or debit() method on user instance
    # to update the balance.
    # This will ensure that the transaction is logged properly.
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MaxValueValidator(settings.MAXIMUM_WALLET_BALANCE),
        ],
        verbose_name="Account Balance (in INR)",
    )
    # minimum balance is the amount that can be in negative,
    # if you want to allow negative balance
    # for the user, set this to a negative value.
    # For example, if you want to allow a maximum of -1000 balance, set this to -1000.00
    # If you want to allow only positive balance, set this to 0.00
    _min_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MaxValueValidator(0.00),
        ],
        verbose_name="Minimum Balance (in negative INR)",
    )
    label_setting = models.OneToOneField(
        LabelSetting,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="user",
    )

    # only for admin
    commission = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(0.00),
        ],
        verbose_name="Commission Rate (in ₹/packet)",
    )

    assigned_admin = models.ForeignKey(
        to="self",
        null=True,
        on_delete=models.SET_NULL,
        related_name="managed_users",
        default=None,
        verbose_name="Assigned Admin",
    )

    # Wordpress Website URL
    woocommerce_website_url = models.URLField(
        default="", blank=True, verbose_name="Wordpress Website URL for integration"
    )
    woocommerce_webhook_secret = models.CharField(
        default="", blank=True, verbose_name="Wordpress Woocommerce Secret Code"
    )

    created_at = models.DateTimeField(verbose_name="Created At", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Updated At", auto_now=True)
    last_order_at = models.DateTimeField(
        verbose_name="Last Order At",
        null=True,
        blank=True,
        default=None,
    )

    # Sales Person
    sales_person = models.CharField(max_length=30, default="")
    cod_remittance_cycle = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        verbose_name="COD Remittance Cycle (D+n days)",
    )

    class Meta:
        ordering = ["-created_at"]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()  # type: ignore

    def __str__(self):
        return self.email

    def get_kyc(self):
        """
        Retrieve or create a KYC (Know Your Customer) record for the current user.

        This method attempts to fetch an existing KYC object associated with the user.
        If no KYC record exists, it creates a new one automatically.

        Returns:
            KYC: The KYC object associated with the user. Either an existing record
                 or a newly created one.
        """
        kyc, _ = KYC.objects.get_or_create(user=self)
        return kyc

    @property
    def is_agreement_accepted(self):
        """
        Check if the KYC agreement has been accepted by the user.

        Retrieves the KYC (Know Your Customer) record associated with this account
        and returns whether the agreement has been accepted.

        Returns:
            bool: True if the agreement has been accepted, False otherwise.
        """
        kyc = self.get_kyc()
        return kyc.is_agreement_accepted

    @property
    def status(self):
        """
        Get the current status of the account.

        Updates the status by calling update_status() and returns the internal status value.

        Returns:
            The current status of the account stored in self._status.
        """
        self.update_status()
        return self._status

    @status.setter
    def status(self, value: str):
        """
        Set the status of the account.
        Args:
            value (str): The status to set. Must be one of the valid status choices defined in STATUS.
        Raises:
            ValueError: If the provided value is not a valid status option.
        """
        if value not in dict(self.STATUS):
            raise ValueError(f"Invalid status: {value}. Must be one of {self.STATUS}.")

        self._status = value

    @property
    def min_balance(self):
        """
        Get the minimum balance.

        Returns:
            The minimum balance value.
        """
        return self._min_balance

    @min_balance.setter
    def min_balance(self, value: float):
        """
        Set the minimum balance for the account.

        Converts the provided value to a negative number by taking its absolute value
        and negating it. This ensures the minimum balance is always stored as a negative value.

        Args:
            value (float): The minimum balance value to set. Can be positive or negative;
                          will be converted to negative format.
        """
        self._min_balance = -abs(to_money(value))

    @property
    def shipzee_code(self) -> str:
        """
        Generate a unique swiftcourier code for the account.

        Returns:
            int: A unique code calculated by adding the account's ID to the base value of 51000.
        """
        if self.role == self.USER:
            prefix = "SCU"
        elif self.role == self.ADMIN:
            prefix = "SCA"
        else:
            prefix = "SCS"

        return f"{prefix}{265254 + self.id}"

    def get_full_address(self) -> str:
        """
        Generate a complete address string by combining address components.

        Concatenates the address, city, state, pin code, and country fields
        into a single formatted string, separated by commas. Only includes
        non-empty address components in the final result.

        Returns:
            str: A comma-separated full address string with empty fields omitted.

        Example:
            >>> address.get_full_address()
            '123 Main Street, New York, NY, 10001, United States'
        """
        address_parts = [
            self.address,
            self.city,
            self.state,
            self.pin_code,
            self.country,
        ]
        return ", ".join(part for part in address_parts if part)

    def get_available_couriers(self) -> list[Courier]:
        """
        Retrieve a list of available couriers from the account's rate cards.
        This method iterates through all associated rate cards and extracts the
        courier information from each one.
        Returns:
            list[Courier]: A list of Courier objects available through the account's
                           rate cards. Returns an empty list if no rate cards are
                           configured.
        """
        couriers = []
        if self.rate_cards:
            for rate_card in self.rate_cards:
                couriers.append(rate_card.courier)

        return couriers

    def update_status(self):
        """
        Update the customer status based on their last order date.
        This method determines the customer's status ('active', 'sleeping', or 'dead')
        based on the time elapsed since their last order:
        - 'active': Last order within the last 7 days
        - 'sleeping': Last order between 7 and 30 days ago
        - 'dead': Last order more than 30 days ago
        The status is only saved to the database if it has changed from the previous value.
        Returns:
            None
        """
        if self.last_order_at:
            new_status = None
            if now() - self.last_order_at > timedelta(days=30):
                new_status = "dead"
            elif now() - self.last_order_at > timedelta(days=7):
                new_status = "sleeping"
            else:
                new_status = "active"

            if new_status != self._status:
                self._status = new_status
                self.save(update_fields=["_status"])

    def save(self, *args, **kwargs):
        """
        Save the model instance to the database.
        If the instance does not have an assigned admin and the email is not the default admin user,
        this method will retrieve or create a default admin user with the email specified in settings.
        If the default admin user is newly created, a password will be set using the credentials from settings.
        The newly created or retrieved default admin user will then be assigned to this instance.
        Args:
            *args: Variable length argument list passed to the parent save method.
            **kwargs: Arbitrary keyword arguments passed to the parent save method.
        """
        if not self.assigned_admin and self.email != settings.DEFAULT_ADMIN_USER:
            default_admin, created = User.objects.get_or_create(
                email=settings.DEFAULT_ADMIN_USER,
                defaults={
                    "full_name": "Default Admin User",
                    "role": User.ADMIN,
                },
            )
            if created:
                default_admin.set_password(settings.DEFAULT_ADMIN_USER_PASSWORD)
                default_admin.save()

            self.assigned_admin = default_admin
        super().save(*args, **kwargs)

    def have_balance(self, amount: float) -> bool:
        """
        Check if the account has sufficient balance after deducting the specified amount.

        Args:
            amount (float): The amount to be deducted from the balance.

        Returns:
            bool: True if the remaining balance would be greater than or equal to
                  the minimum balance threshold, False otherwise.
        """
        return (self.balance - to_money(amount)) >= self.min_balance

    def credit(self, amount: float) -> bool:
        """
        Add credit to the wallet balance.
        Args:
            amount (float): The amount to add to the wallet balance.
        Returns:
            bool: True if the credit was successfully added, False if it would exceed
                  the maximum wallet balance limit.
        Raises:
            None
        Note:
            The balance is rounded to 2 decimal places and persisted to the database
            upon successful credit.
        """
        # Row-locked read-modify-write so concurrent credits/debits (multiple
        # gunicorn workers + celery) cannot lose an update. Re-reads the
        # authoritative balance inside the lock and writes only the balance
        # column, never the whole user row.
        amount = to_money(amount)
        # A wallet movement is always a positive quantity; the direction lives in
        # transaction_type. A <= 0 credit means a bad rate card / price_breakup
        # upstream and would silently move the balance the wrong way.
        if amount <= 0:
            logger.error("User %s: refusing to credit non-positive %s", self.pk, amount)
            return False
        with db_transaction.atomic():
            user = User.objects.select_for_update().get(pk=self.pk)
            if (user.balance + amount) > to_money(settings.MAXIMUM_WALLET_BALANCE):
                return False
            user.balance = to_money(user.balance + amount)
            user.save(update_fields=["balance"])
        self.balance = user.balance
        return True

    def debit(self, amount: float, forcefully=False) -> bool:
        """
        Add debit to the wallet balance.
        Args:
            amount (float): The amount to debit from the wallet balance.
            forcefully (bool): If you dont want to check if user have balance or not just debit from their balance (used for debitting rto charges)
        Returns:
            bool: True if the debit was successfully added, False if it would exceed
                  the maximum wallet balance limit.
        Raises:
            None
        Note:
            The balance is rounded to 2 decimal places and persisted to the database
            upon successful credit.
        """

        # Row-locked read-modify-write (see credit()). The balance check is
        # re-done inside the lock so a stale have_balance() call by the caller
        # can never let the wallet overdraw.
        amount = to_money(amount)
        if amount <= 0:
            logger.error("User %s: refusing to debit non-positive %s", self.pk, amount)
            return False
        with db_transaction.atomic():
            user = User.objects.select_for_update().get(pk=self.pk)
            if not forcefully and (user.balance - amount) < user.min_balance:
                return False
            user.balance = to_money(user.balance - amount)
            user.save(update_fields=["balance"])
        self.balance = user.balance
        return True

    def get_label_setting(self) -> LabelSetting:
        """
        Retrieve or create the LabelSetting associated with the user.
        """
        # Check if the user already has a label setting
        if not self.label_setting:
            # Create a new LabelSetting instance
            label_setting = LabelSetting.objects.create()
            # Assign it to the user's label_setting field
            self.label_setting = label_setting
            self.save()
        return self.label_setting

    def get_courier_preference(self) -> list[Courier]:
        """
        Returns a list of Courier objects based on the user's courier preference sequences,
        ordered by their position.

        Iterates through the related courier_preference_sequences, orders them by the 'position'
        attribute, and collects the associated Courier objects.

        Returns:
            list[Courier]: Ordered list of preferred Courier objects.
        """
        courier_preference = []

        for sequence in self.courier_preference_sequences.order_by("position"):
            courier_preference.append(sequence.courier)

        return courier_preference

    def set_courier_preference(self, courier_list: list[Courier]) -> None:
        """
        Sets the user's courier preferences based on the provided list of Courier objects.

        Clears any existing preferences and creates new CourierPreferenceSequence entries
        for each Courier in the provided list, assigning positions based on their order
        in the list.

        Args:
            courier_list (list[Courier]): List of Courier objects representing the user's preferences.
        """
        # Clear existing preferences
        self.courier_preference_sequences.all().delete()

        # Create new preferences with updated positions
        for position, courier in enumerate(courier_list):
            CourierPreferenceSequence.objects.create(
                user=self, courier=courier, position=position
            )


class KYC(MyModel):
    """
    Model representing Know Your Customer (KYC) information for a user account.
    """

    AVAILABLE_STATUS = ("pending", "submitted", "approved", "rejected")
    STATUS = ((i, i.capitalize()) for i in AVAILABLE_STATUS)

    user = models.OneToOneField(to=User, on_delete=models.PROTECT, related_name="_kyc")
    _status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="pending",
    )
    _is_agreement_accepted = models.BooleanField(default=False)
    kyc_form_submitted_at = models.DateTimeField(null=True, blank=True)
    # KYC Approved By
    approved_by = models.CharField(max_length=30, default="")

    @property
    def is_kyc_verified(self) -> bool:
        """
        Check if the KYC status is approved.
        """
        return self._status == "approved"

    @property
    def is_agreement_accepted(self) -> bool:
        """Check if the user has accepted the KYC agreement."""
        return self._is_agreement_accepted

    @is_agreement_accepted.setter
    def is_agreement_accepted(self, value: bool) -> None:
        """Set the KYC agreement acceptance status."""
        self._is_agreement_accepted = value

    @property
    def status(self) -> str:
        """Get the current KYC status."""
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        """Set the KYC status, ensuring it is a valid option."""
        if value not in self.AVAILABLE_STATUS:
            raise ValueError(f"Invalid status: {value}")
        self._status = value

    def submit_kyc(self):
        """Submit the KYC form, updating the submission timestamp and status."""
        self.kyc_form_submitted_at = now()
        if self._status != "approved":
            self._status = "submitted"
        self.save()


class CourierPreferenceSequence(MyModel):
    """Model representing a user's preference sequence for couriers."""

    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="courier_preference_sequences"
    )
    courier = models.ForeignKey(
        to=Courier, related_name="user_preferences", on_delete=models.CASCADE
    )
    # position starts from 0
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        unique_together = ("user", "courier")

    @staticmethod
    def create_or_update_preference(user: User, couriers: list[Courier]):
        """
        Create or update the courier preference sequence for a user.

        Args:
            user (User): The user for whom to create or update the preference.
            couriers (list[Courier]): List of Courier objects in the desired order of preference.
        """
        # Clear existing preferences
        CourierPreferenceSequence.objects.filter(user=user).delete()

        # Create new preferences with updated positions
        for position, courier in enumerate(couriers):
            CourierPreferenceSequence.objects.create(
                user=user, courier=courier, position=position
            )

    @staticmethod
    def get_user_preference(user: User) -> list[Courier]:
        """
        Get the courier preference sequence for a user.

        Args:
            user (User): The user for whom to get the preference.
        """
        preferences = CourierPreferenceSequence.objects.filter(user=user).order_by(
            "position"
        )
        return [preference.courier for preference in preferences]

    def __str__(self):
        return f"CourierPreference({self.user.email} - {self.courier.name})"


class Notification(MyModel):
    """Model representing a notification for a user."""

    CATEGORY = (
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("success", "Success"),
    )
    COLOR_CLASSES = {
        "info": "bg-green-100 text-green-800",
        "warning": "bg-red-100 text-red-800",
        "error": "bg-yellow-100 text-yellow-800",
        "success": "bg-blue-100 text-blue-800",
    }
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="notifications"
    )
    msg = models.TextField()
    is_read = models.BooleanField(default=False)
    category = models.CharField(max_length=20, choices=CATEGORY, default=CATEGORY[0][0])
    read_at = models.DateTimeField(
        null=True, blank=True, default=None, verbose_name="Read At"
    )

    def __str__(self):
        return f"Notification({self.msg} for {self.user.email})"

    @property
    def color_class(self):
        """Get the CSS class for the notification based on its category."""
        return self.COLOR_CLASSES.get(self.category, "bg-gray-100 text-gray-800")


class ConfirmEmail(MyModel):
    """Model representing an email confirmation OTP for a user."""

    otp = models.IntegerField()
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    attempts = models.IntegerField(default=0)

    def is_expired(self):
        """Check if the OTP has expired.

        The OTP is considered expired if the current time is greater than
        the time of creation plus the specified expiration time in days.

        The expiration time is specified in the SITE_SETTINGS dictionary
        in settings.py. If the 'expire_in' key is not present, the default
        expiration time is 10 days.

        Returns:
            bool: True if the OTP has expired, False otherwise.
        """
        return now() > self.created_at + timedelta(
            days=settings.SITE_SETTINGS["email"].get("expire_in", 10)
        )


class PasswordReset(MyModel):
    """Model representing a password reset token for a user."""

    token = models.UUIDField(default=uuid.uuid4)
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)

    def is_expired(self):
        """Check if the password reset token has expired.

        The token is considered expired if the current time is greater than
        the time of creation plus the specified expiration time in days.

        The expiration time is specified in the SITE_SETTINGS dictionary
        in settings.py. If the 'expire_in' key is not present, the default
        expiration time is 10 days.

        Returns:
            bool: True if the token has expired, False otherwise.
        """
        return now() > self.created_at + timedelta(
            days=settings.SITE_SETTINGS["email"].get("expire_in", 10)
        )


class Activity(MyModel):
    """Model representing a user activity log."""

    ACTIVITY_TYPES = (
        ("login", "Login"),
        ("logout", "Logout"),
        ("password_change", "Password Change"),
        ("profile_update", "Profile Update"),
        ("email_change", "Email Change"),
        ("merchant_info_update", "Merchant Info Update"),
        ("label_setting_update", "Label Setting Update"),
    )
    COLOR_CLASSES = {
        "login": "primary",
        "logout": "danger",
        "password_change": "warning",
        "profile_update": "black",
        "email_change": "info",
        "merchant_info_update": "info",
        "label_setting_update": "info",
    }
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="activities"
    )
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    activity_description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(
        null=True, blank=True, default=None, verbose_name="Read At"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Activity({self.activity_type} for {self.user.email})"

    @property
    def color_class(self):
        """Get the CSS class for the activity based on its type."""
        return self.COLOR_CLASSES.get(self.activity_type, "bg-gray-100 text-gray-800")

    @staticmethod
    def create(
        user: User,
        activity_type: str,
        activity_description: str,
        ip_address: str = None,
    ):
        """Create a new activity record."""
        activity = Activity(
            user=user,
            activity_type=activity_type,
            activity_description=activity_description,
            ip_address=ip_address,
        )
        activity.save()
        return activity

    @staticmethod
    def create_from_request(
        request,
        activity_type: str,
        activity_description: str,
        user: User = None,
    ):
        """Create a new activity record from an HTTP request."""
        ip_address = request.META.get("HTTP_X_FORWARDED_FOR", None) or request.META.get(
            "REMOTE_ADDR"
        )
        return Activity.create(
            user=user or request.user,
            activity_type=activity_type,
            activity_description=activity_description,
            ip_address=ip_address,
        )


class BlockedPincode(MyModel):
    """
    Model to store blocked pincodes.
    This is used to prevent shipments to certain pincodes.
    """

    country = models.CharField(
        max_length=30, default="india", verbose_name="Country", blank=True
    )
    pincode = models.CharField(max_length=6, unique=True, verbose_name="Pincode")
    reason = models.TextField(
        blank=True, default="N/A", verbose_name="Reason for Blocking"
    )
    blocked_for = models.CharField(
        max_length=10,
        choices=(("all", "All Users"), ("specific", "Specific Users")),
        default="all",
    )
    blocked_users = models.ManyToManyField(
        to=User,
        related_name="blocked_pincodes",
        verbose_name="Blocked For",
    )

    blocked_by = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Blocked By",
    )

    def __str__(self):
        return f"{self.pincode} - {self.country}"

    @staticmethod
    def block_pincode(
        pincode: str, country: str = "india", reason: str = "", blocked_by: User = None
    ) -> "BlockedPincode":
        """
        Block a pincode.

        Args:
            pincode (str): The pincode to block.
            country (str): The country of the pincode. Defaults to "india".
            reason (str): The reason for blocking the pincode. Defaults to "".
            blocked_by (User): The user who is blocking the pincode. Defaults to None.

        Returns:
            BlockedPincode: The created BlockedPincode instance.
        """
        blocked_pincode, created = BlockedPincode.objects.get_or_create(
            pincode=pincode,
            country=country,
            defaults={"reason": reason, "blocked_by": blocked_by},
        )
        if not created:
            blocked_pincode.reason = reason
            blocked_pincode.blocked_by = blocked_by
            blocked_pincode.save()

        return blocked_pincode

    @staticmethod
    def unblock_pincodes(pincodes: list[str], country: str = "india") -> bool:
        """
        Unblock a pincode.

        Args:
            pincode (str): The pincode to unblock.
            country (str): The country of the pincode. Defaults to "india".

        Returns:
            bool: True if the pincode was unblocked, False if it was not found.
        """
        try:
            blocked_pincodes = BlockedPincode.objects.filter(
                pincode__in=pincodes, country=country
            )
            blocked_pincodes.delete()
            return True
        except Exception:
            return False


class SubscribeNewsletter(MyModel):
    """Model representing a newsletter subscription."""

    _email = models.EmailField(unique=True)
    _is_subscribed = models.BooleanField(default=True)

    def __str__(self):
        return self._email

    @staticmethod
    def subscribe(email: str) -> "SubscribeNewsletter":
        """Subscribe an email to the newsletter.
        If the email is already subscribed, it will not create a new entry."""
        return SubscribeNewsletter.objects.get_or_create(_email=email)

    @staticmethod
    def unsubscribe(email: str) -> bool:
        """Unsubscribe an email from the newsletter.
        Returns True if successful, False otherwise."""
        try:
            sn = SubscribeNewsletter.objects.get(_email=email)
            sn._is_subscribed = False
            sn.save()
            return True
        except Exception:
            return False


class ContactUs(MyModel):
    """Model representing a contact us request or a quote request."""

    _AVAILABLE_COURIER_TYPE = {
        "express": "Express",
        "international": "International",
        "pallet": "Pallet",
        "ware_housing": "Ware Housing",
        "other": "Other",
    }
    COURIER_TYPE = list(_AVAILABLE_COURIER_TYPE.items())
    _name = models.CharField(max_length=30)
    _contact_no = models.CharField(max_length=15)
    _subject = models.CharField(max_length=50)
    _message = models.TextField()
    _courier_type = models.TextField(
        choices=COURIER_TYPE, null=True, blank=True, default=None
    )
    _is_request_a_quote = models.BooleanField(default=False)

    def __str__(self):
        return self._contact_no

    @staticmethod
    def add_contact_us_request(
        name: str, contact_no: str, subject: str, message: str
    ) -> "ContactUs":
        """Add a contact us request."""
        return ContactUs.objects.create(
            _name=name,
            _contact_no=contact_no,
            _subject=subject,
            _message=message,
            _is_request_a_quote=False,
        )

    @staticmethod
    def add_get_a_quote(
        name: str, contact_no: str, subject: str, message: str, courier_type: str
    ) -> "ContactUs":
        """Add a get a quote request."""
        return ContactUs.objects.create(
            _name=name,
            _contact_no=contact_no,
            _subject=subject,
            _message=message,
            _courier_type=(
                courier_type
                if courier_type in ContactUs._AVAILABLE_COURIER_TYPE
                else "other"
            ),
            _is_request_a_quote=True,
        )


class Invoice(MyModel):
    number = models.CharField(max_length=20, unique=True)
    service_type = models.CharField(max_length=20)
    date_from = models.DateField(
        verbose_name="Invoice Date From", null=True, default=None
    )
    date_to = models.DateField(verbose_name="Invoice Date To", null=True, default=None)
    period = models.DateTimeField()
    amount = models.FloatField(default=0.0)
    pdf_file = models.FileField(upload_to="invoices/", blank=True)
    excel_file = models.FileField(upload_to="invoices/", blank=True)
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)

    @classmethod
    def get_for_a_user(cls, user: User):
        return cls.objects.filter(user=user)

    @classmethod
    def get_latest_of_a_user(cls, user: User):
        return cls.get_for_a_user(user).latest()


class Notice(MyModel):
    notice = models.TextField()
    end_date = models.DateField()

    def __str__(self):
        return f"Notice(msg={self.notice})"

    @classmethod
    def get_active_notice(cls):
        today = now().date()
        return cls.objects.filter(end_date__gte=today).order_by("-id").values("notice")


class ImpersonationToken(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    target_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="impersonation_tokens"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="issued_impersonation_tokens"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def is_valid(self):
        # Token expires in 2 minutes and can only be used once
        return not self.used and now() < self.created_at + timedelta(minutes=2)
