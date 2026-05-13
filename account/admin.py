from import_export.admin import ImportExportModelAdmin
from django.contrib import admin
from .models import (
    KYC,
    BlockedPincode,
    ContactUs,
    Invoice,
    Notice,
    RateCard,
    SubscribeNewsletter,
    User,
    Notification,
    ConfirmEmail,
    PasswordReset,
    Activity,
    LabelSetting,
    Courier,
)


class MyModelAdmin(ImportExportModelAdmin):
    list_per_page = 25
    search_fields = ["id"]  # Override in child if needed
    list_filter = ["created_at", "updated_at"]  # Override in child if needed
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]

    def get_search_fields(self, request):
        return getattr(self, "search_fields", super().get_search_fields(request))

    def get_list_filter(self, request):
        return getattr(self, "list_filter", super().get_list_filter(request))

    def get_ordering(self, request):
        return getattr(self, "ordering", super().get_ordering(request))


@admin.register(Notice)
class NoticeAdmin(MyModelAdmin):
    list_display = (
        "id",
        "notice",
        "end_date",
    )


@admin.register(LabelSetting)
class LabelSettingAdmin(MyModelAdmin):
    list_display = (
        "id",
        "show_logo",
        "show_support_info",
        "show_customer_mobile",
        "show_pickup_address",
    )


@admin.register(Invoice)
class InvoiceAdmin(MyModelAdmin):
    list_display = (
        "number",
        "user",
        "service_type",
        "date_from",
        "date_to",
        "amount",
    )


@admin.register(Courier)
class CourierAdmin(MyModelAdmin):
    list_display = (
        "id",
        "name",
        "abbreviation",
        "integration_path",
        "active",
    )
    search_fields = ("name", "contact_phone")
    list_filter = ("active",)


# Register your models here.
@admin.register(User)
class UserAdmin(MyModelAdmin):
    list_display = ("id", "full_name", "email", "date_joined", "last_login", "is_staff")


@admin.register(KYC)
class KYCAdmin(MyModelAdmin):
    list_display = ("id", "user", "kyc_form_submitted_at")


@admin.register(Notification)
class NotificationAdmin(MyModelAdmin):
    list_display = ("id", "user", "msg", "is_read", "created_at")


@admin.register(Activity)
class ActivityAdmin(MyModelAdmin):
    list_display = ("id", "user", "activity_type", "is_read", "created_at")


@admin.register(ConfirmEmail)
class ConfirmEmailAdmin(MyModelAdmin):
    list_display = ("id", "user", "attempts", "created_at")


@admin.register(PasswordReset)
class PasswordResetAdmin(MyModelAdmin):
    list_display = ("id", "user", "created_at")


@admin.register(RateCard)
class RateCardAdmin(MyModelAdmin):
    list_display = (
        "id",
        "user",
        "courier",
        "created_at",
    )


@admin.register(BlockedPincode)
class BlockedPincodeAdmin(MyModelAdmin):
    list_display = (
        "pincode",
        "reason",
        "blocked_by",
    )


@admin.register(SubscribeNewsletter)
class SubscribeNewsletterAdmin(MyModelAdmin):
    list_display = (
        "_email",
        "_is_subscribed",
    )


@admin.register(ContactUs)
class ContactUsAdmin(MyModelAdmin):
    list_display = (
        "_name",
        "_contact_no",
        "_subject",
    )
