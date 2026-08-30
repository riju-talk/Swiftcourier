from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderResponse:
    success: bool
    message_id: str = ""
    status: str = ""
    raw: Any = None
    error: str = ""


class WhatsAppProvider:
    name = "base"

    def send_message(self, to_number: str, body: str) -> ProviderResponse:
        raise NotImplementedError
