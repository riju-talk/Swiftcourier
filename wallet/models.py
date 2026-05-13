from django.db import models
from account.models import MyModel, Notification


# Create your models here.
class Transaction(MyModel):
    """
    Transaction model to store transaction details.
    """

    TRANSACTION_TYPES = (
        ("credit", "Credit"),
        ("debit", "Debit"),
    )
    TRANSACTION_DESCRIPTIONS = (
        ("wallet_recharge", "Wallet Recharge"),
        ("commission", "Commission"),
        ("shipping_charges", "Shipping Charges"),
        ("cancelled_order", "Cancelled Order"),
        ("rto_charges", "RTO Charges"),
        ("freight_adjusted", "Freight Adjusted"),
        ("excess_weight_charges", "Excess Weight Charges"),
        ("other", "Other"),
    )
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("SUCCESS", "Success"),
        ("FAILED", "Failed"),
    )

    transaction_type = models.CharField(max_length=6, choices=TRANSACTION_TYPES)
    # amount is stored in rupees
    amount = models.FloatField()
    closing_amount = models.FloatField(default=0)
    desc = models.CharField(
        max_length=255,
        blank=True,
        default=TRANSACTION_DESCRIPTIONS[0][0],
        choices=TRANSACTION_DESCRIPTIONS,
    )
    other_reason = models.TextField(blank=True, default="", help_text="Provide reason if description is 'Other'")
    merchant_transaction_id = models.CharField(max_length=100, default="", unique=True)
    user = models.ForeignKey(
        "account.User", on_delete=models.CASCADE, related_name="transactions"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    json = models.JSONField(default=dict)

    # Add any additional fields you need for the transaction
    def __str__(self):
        return f"{self.transaction_type} - {self.amount} - {self.user.email}"

    @staticmethod
    def create_transaction(
        user,
        merchant_txn_id: str,
        amount_rs: float,
        desc: str = "wallet_recharge",
        transaction_type="credit",
        json: dict = {},
        other_reason: str = "",
    ) -> "Transaction":
        return Transaction.objects.create(
            merchant_transaction_id=str(user.id) + merchant_txn_id,
            amount=amount_rs,
            status="PENDING",
            user=user,
            transaction_type=transaction_type,
            desc=desc,
            json=json,
            other_reason=other_reason,
        )

    def credit(
        self,
        status="SUCCESS",
        forcefully=False,
        awb_number=None,
        json: dict | None = None,
    ) -> bool:
        """
        Credits the specified amount to the user's account and updates the transaction status.

        Args:
            status (str, optional): The status to set for the transaction. Defaults to "SUCCESS".
            forcefully (bool, optional): If True, credits the amount regardless of the current transaction status. Defaults to False.

        Returns:
            bool: True if the credit operation was successful and the transaction was updated, False otherwise.
        """
        if forcefully:
            if not self.user.credit(self.amount):
                return False
        else:
            if self.status != "PENDING" or not self.user.credit(self.amount):
                return False

        self.closing_amount = self.user.balance
        self.status = status
        if json is not None:
            self.json |= json
        self.save()

        msg = f"Transaction of {round(self.amount, 2)} was {status.lower()}; Reason: {self.get_desc_display()}"
        if awb_number:
            msg += f"; AWB Number: {awb_number}"

        Notification.objects.create(
            user=self.user,
            category="info",
            msg=msg,
        )

        return True

    def debit(self, status="SUCCESS", forcefully=False, awb_number=None, json: dict | None = None) -> bool:
        """
        Debits the specified amount from the user's balance and updates the transaction status.

        Args:
            status (str, optional): The status to set for the transaction. Defaults to "SUCCESS".
            forcefully (bool, optional): If True, debit is attempted regardless of transaction status. Defaults to False.

        Returns:
            bool: True if the debit was successful and transaction was updated, False otherwise.
        """
        if forcefully:
            if not self.user.debit(self.amount, forcefully=True):
                return False
        else:
            if self.status != "PENDING" or not self.user.debit(self.amount):
                return False

        self.closing_amount = self.user.balance
        self.status = status
        if json is not None:
            self.json |= json
        self.save()

        msg = f"Transaction of {round(self.amount, 2)} was {status.lower()}; Reason: {self.get_desc_display()}"
        if awb_number:
            msg += f"; AWB Number: {awb_number}"

        Notification.objects.create(
            user=self.user,
            category="info",
            msg=msg,
        )

        return True
