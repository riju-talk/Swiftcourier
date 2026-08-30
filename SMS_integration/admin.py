from django.contrib import admin

from .models import (
    SMSNotificationLog,
    SMSSettings,
    SMSStatusConfig,
    SMSTemplate,
)


@admin.register(SMSSettings)
class SMSSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled", "provider", "default_rate", "monthly_cap")
    search_fields = ("user__email",)


@admin.register(SMSTemplate)
class SMSTemplateAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "version", "is_active")
    search_fields = ("user__email", "status")


@admin.register(SMSStatusConfig)
class SMSStatusConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "enabled", "cost_per_message")
    search_fields = ("user__email", "status")


@admin.register(SMSNotificationLog)
class SMSNotificationLogAdmin(admin.ModelAdmin):
    list_display = ("user", "order", "status", "send_status", "delivery_status", "created_at")
    search_fields = ("user__email", "order__id", "provider_message_id")
    list_filter = ("send_status", "delivery_status", "status")
