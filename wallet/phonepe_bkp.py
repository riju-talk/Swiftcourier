# phonepe.py
import json
import base64
import hashlib
import uuid
import requests
from django.urls import reverse
from django.conf import settings

from .models import Transaction


def generate_merchant_txn_id() -> str:
    return str(uuid.uuid4())


def create_transaction(user, merchant_txn_id: str, amount_rs: float) -> Transaction:
    return Transaction.objects.create(
        merchant_transaction_id=merchant_txn_id,
        amount=amount_rs,
        status="PENDING",
        user=user,
        transaction_type="credit",
        desc="PhonePe transaction",
    )


def prepare_payload(request, user_id: int, merchant_txn_id: str, amount_paise: int) -> str:
    payload = {
        "merchantId": settings.PHONEPE_MERCHANT_ID,
        "merchantTransactionId": merchant_txn_id,
        "merchantUserId": str(user_id),
        "amount": amount_paise,
        "callbackUrl": request.build_absolute_uri(reverse("wallet:callback")),
        "redirectUrl": request.build_absolute_uri(reverse("wallet:redirect")),
        "redirectMode": "GET",
        "paymentInstrument": {"type": "PAY_PAGE"},
    }
    payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return base64.b64encode(payload_str.encode()).decode()


def compute_request_x_verify(b64_payload: str) -> str:
    to_sign = b64_payload + "/pg/v1/pay" + settings.PHONEPE_SALT_KEY
    sha = hashlib.sha256(to_sign.encode()).hexdigest()
    return f"{sha}###{settings.PHONEPE_SALT_INDEX}"


def initiate_payment(b64_payload: str, x_verify: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "X-VERIFY": x_verify,
    }
    resp = requests.post(
        settings.PHONEPE_PAY_ENDPOINT, json={"request": b64_payload}, headers=headers
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"]["instrumentResponse"]["redirectInfo"]["url"]


def verify_callback_signature(encoded_resp: str, received_x_verify: str) -> bool:
    expected_hash = hashlib.sha256(
        (encoded_resp + settings.PHONEPE_SALT_KEY).encode()
    ).hexdigest()
    expected_x_verify = f"{expected_hash}###{settings.PHONEPE_SALT_INDEX}"
    return expected_x_verify == received_x_verify


def decode_callback_payload(encoded_resp: str) -> dict:
    return json.loads(base64.b64decode(encoded_resp))


def update_transaction_status(callback_data: dict):
    data = callback_data.get("data", {})
    mtid = data.get("merchantTransactionId")
    tx = Transaction.objects.get(merchant_transaction_id=mtid)
    tx.status = (
        "SUCCESS"
        if (
            callback_data.get("success")
            and callback_data.get("code") == "PAYMENT_SUCCESS"
        )
        else "FAILED"
    )
    tx.phonepe_transaction_id = data.get("transactionId")
    tx.save()
