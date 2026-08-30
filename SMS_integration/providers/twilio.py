import requests

from .base import ProviderResponse, SMSProvider


class TwilioProvider(SMSProvider):
    name = "twilio"

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    def send_message(self, to_number: str, body: str) -> ProviderResponse:
        if not self.account_sid or not self.auth_token or not self.from_number:
            return ProviderResponse(
                success=False,
                error="Twilio credentials missing",
            )

        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        )
        payload = {
            "From": self.from_number,
            "To": to_number,
            "Body": body,
        }

        try:
            response = requests.post(
                url,
                data=payload,
                auth=(self.account_sid, self.auth_token),
                timeout=30,
            )
        except Exception as exc:
            return ProviderResponse(success=False, error=str(exc))

        if 200 <= response.status_code < 300:
            data = response.json()
            return ProviderResponse(
                success=True,
                message_id=data.get("sid", ""),
                status=data.get("status", "sent"),
                raw=data,
            )

        return ProviderResponse(
            success=False,
            error=response.text,
            raw={"status_code": response.status_code, "body": response.text},
        )
