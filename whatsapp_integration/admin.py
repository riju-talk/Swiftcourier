from django.contrib import admin

from .models import (
    WhatsAppNotificationLog,
    WhatsAppSettings,
    WhatsAppStatusConfig,
    WhatsAppTemplate,
)


@admin.register(WhatsAppSettings)
class WhatsAppSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled", "provider", "default_rate", "monthly_cap")
    search_fields = ("user__email",)


@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "version", "is_active")
    search_fields = ("user__email", "status")


@admin.register(WhatsAppStatusConfig)
class WhatsAppStatusConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "enabled", "cost_per_message")
    search_fields = ("user__email", "status")


@admin.register(WhatsAppNotificationLog)
class WhatsAppNotificationLogAdmin(admin.ModelAdmin):
    list_display = ("user", "order", "status", "send_status", "delivery_status", "created_at")
    search_fields = ("user__email", "order__id", "provider_message_id")
    list_filter = ("send_status", "delivery_status", "status")
