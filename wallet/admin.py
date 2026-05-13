from django.contrib import admin

from account.admin import MyModelAdmin
from .models import Transaction


# Register your models here.
@admin.register(Transaction)
class TransactionAdmin(MyModelAdmin):
    list_display = (
        "id",
        "merchant_transaction_id",
        "amount",
        "status",
        "transaction_type",
        "user",
    )
    list_filter = ["desc", "created_at", "updated_at", "user"]
