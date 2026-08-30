from django.conf import settings

from .base import WhatsAppProvider
from .twilio import TwilioProvider


def get_provider(settings_obj) -> WhatsAppProvider:
    provider = (settings_obj.provider or "twilio").lower()
    if provider == "twilio":
        return TwilioProvider(
            account_sid=getattr(settings, "TWILIO_ACCOUNT_SID", ""),
            auth_token=getattr(settings, "TWILIO_AUTH_TOKEN", ""),
            from_number=getattr(settings, "TWILIO_WHATSAPP_NUMBER", ""),
        )
    raise ValueError(f"Unsupported provider: {provider}")
