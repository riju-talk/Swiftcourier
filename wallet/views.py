import json
import logging
import razorpay
from uuid import uuid4

from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages

from account.decorators import user_required
from django.contrib.auth.decorators import login_required
from .models import Transaction
from phonepe.sdk.pg.payments.v2.standard_checkout_client import StandardCheckoutClient
from phonepe.sdk.pg.common.models.request.meta_info import MetaInfo
from phonepe.sdk.pg.payments.v2.models.request.standard_checkout_pay_request import (
    StandardCheckoutPayRequest,
)

mylogger = logging.getLogger("my-logger")

# Initialize PhonePe client with settings from Django settings
client = StandardCheckoutClient.get_instance(
    client_id=settings.PHONEPE_CLIENT_ID,
    client_secret=settings.PHONEPE_CLIENT_SECRET,
    client_version=settings.PHONEPE_CLIENT_VERSION,
    env=settings.PHONEPE_ENV,
    should_publish_events=settings.PHONEPE_SHOULD_PUBLISH_EVENTS,
)
rz_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)
rz_client.enable_retry(True)
rz_client.set_app_details({"title": "IdiotShip", "version": "1.0"})


@user_required
def checkout(request):
    # 1. Validate amount
    try:
        amount_rs = float(request.GET.get("amount", ""))
    except ValueError:
        return HttpResponse("Invalid amount", status=400)
    amount_paise = int(amount_rs * 100)

    # 2. Create transaction record
    trx = Transaction.create_transaction(
        user=request.user,
        merchant_txn_id=str(request.user.id) + str(uuid4()),
        amount_rs=amount_rs,
        desc="wallet_recharge",
        transaction_type="credit",
    )

    # 4. Call PhonePe and redirect user
    try:
        standard_pay_request = StandardCheckoutPayRequest.build_request(
            merchant_order_id=trx.merchant_transaction_id,
            amount=amount_paise,
            redirect_url=request.build_absolute_uri(
                reverse(
                    "wallet:redirect",
                    kwargs={"merchant_txn_id": trx.merchant_transaction_id},
                )
            ),
            meta_info=MetaInfo(
                udf1=request.user.id,
                udf2=request.user.email,
            ),
        )
        standard_pay_response = client.pay(standard_pay_request)
        pay_url = standard_pay_response.redirect_url
        trx.json = {
            "state": standard_pay_response.state,
            "redirect_url": standard_pay_response.redirect_url,
            "order_id": standard_pay_response.order_id,
            "expire_at": standard_pay_response.expire_at,
        }
        trx.save()
    except Exception as e:
        return HttpResponse(f"PhonePe API error: {e}", status=500)

    return redirect(pay_url)


@csrf_exempt
def payment_redirect(request, merchant_txn_id: str):
    try:
        t = Transaction.objects.get(
            merchant_transaction_id=merchant_txn_id, user=request.user
        )
    except Transaction.DoesNotExist:
        messages.error(request, "Transaction not found")
        return redirect("index")

    try:
        get_order_status = client.get_order_status(merchant_txn_id)

        if get_order_status.state == "COMPLETED":
            if get_order_status.amount == int(t.amount * 100):
                if t.status == "PENDING" and not t.credit():
                    messages.error(request, "Failed to credit your wallet")
                    return redirect("index")

                messages.success(request, "Payment successful")
                t.status = "SUCCESS"

        elif get_order_status.state == "FAILED":
            t.status = "FAILED"
            messages.error(request, "Payment failed")

        else:
            messages.error(request, f"Payment failed: {get_order_status.error_code}")

        t.json |= get_order_status.to_dict()
        t.save()
    except Exception as e:
        messages.error(request, f"Error saving transaction: {e}")

    return redirect("index")


@csrf_exempt
def callback(request):
    # 1. Must be a POST with a non-empty body
    if request.method != "POST" or not request.body:
        return HttpResponseBadRequest("Invalid request")

    # 2. Parse the wrapper JSON
    try:
        incoming = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Malformed JSON")

    mylogger.debug(f"Incoming callback data: {incoming}")

    # encoded_resp = incoming.get("response", "")
    # received_xv = request.headers.get("X-VERIFY", "")

    # # 3. Verify signature
    # if not verify_callback_signature(encoded_resp, received_xv):
    #     mylogger.debug("Signature invalid")
    #     return HttpResponseBadRequest("Invalid signature")

    # # 4. Decode the inner payload
    # try:
    #     decoded = decode_callback_payload(encoded_resp)
    #     """
    #     {
    #         "success": True,
    #         "code": "PAYMENT_SUCCESS",
    #         "message": "Your payment is successful.",
    #         "data": {
    #             "merchantId": "PGTESTPAYUAT86",
    #             "merchantTransactionId": "fc3562b4-582d-463e-bab6-d11d03b8e449",
    #             "transactionId": "T2505131143407936017773",
    #             "amount": "200000",
    #             "state": "COMPLETED",
    #             "responseCode": "SUCCESS",
    #             "paymentInstrument": {
    #                 "type": "NETBANKING",
    #                 "pgTransactionId": "1995464773",
    #                 "pgServiceTransactionId": "PG2212291607083344934300",
    #                 "bankTransactionId": None,
    #                 "bankId": None,
    #             },
    #         },
    #     }
    #     """
    # except Exception as e:
    #     mylogger.debug(f"Error decoding base64 payload: {e}")
    #     return HttpResponseBadRequest("Invalid base64 payload")

    # # 5. Find and update the Transaction
    # mtid = decoded.get("data", {}).get("merchantTransactionId")
    # try:
    #     tx = Transaction.objects.get(merchant_transaction_id=mtid)

    #     if tx.status != "PENDING":
    #         mylogger.debug("Duplicate transaction: {mtid}")
    #         return HttpResponseBadRequest("Duplicate transaction")
    # except Transaction.DoesNotExist:
    #     mylogger.debug("Unknown transaction:", mtid)
    #     return HttpResponseBadRequest("Unknown transaction")

    # # 6. Store both raw and decoded into your json field
    # tx.json = decoded

    # # 7. Map PhonePe response to your status choices
    # if not decoded["success"]:
    #     tx.status = "FAILED"
    #     tx.save()
    #     return HttpResponse("OK, Failed")

    # amount = int(decoded["data"]["amount"])
    # expected_amount = int(tx.amount * 100)
    # if amount != expected_amount:
    #     mylogger.debug(f"Amount mismatch, expected: {expected_amount}. Got: {amount}")
    #     raise Exception("Amount mismatch")

    # if not tx.credit():
    #     return HttpResponse("OK, Failed")

    # return HttpResponse("OK, Success")

    # Crediting is handled server-side by payment_redirect(), which verifies
    # the transaction directly against PhonePe's get_order_status API rather
    # than trusting this callback body. This endpoint just needs to
    # acknowledge receipt so PhonePe doesn't retry/alert on it.
    return HttpResponse("OK")


@login_required
def add_money(request):
    ctx = {
        "key_id": settings.RAZORPAY_KEY_ID,
        "callback_url": request.build_absolute_uri(
            reverse("wallet:verify-razorpay-transaction")
        ),
    }
    return render(request, "wallet/add_money.dj", ctx)


@login_required
def create_razorpay_transaction(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid method")

    amount_rs = request.GET.get("amount", "")
    try:
        amount_rs = float(amount_rs)
    except ValueError:
        return HttpResponseBadRequest("Invalid amount")

    amount = int(amount_rs * 100)  # Convert to paise
    currency = "INR"

    order_data = {"amount": amount, "currency": currency}
    razorpay_order = rz_client.order.create(data=order_data)

    trxn = Transaction.create_transaction(
        user=request.user,
        merchant_txn_id=razorpay_order["id"],
        amount_rs=amount_rs,
        desc="wallet_recharge",
        transaction_type="credit",
        json={
            "razorpay_order_creation_data": razorpay_order,
        },
    )
    return JsonResponse(
        {
            "order_id": razorpay_order["id"],
            "amount": amount,
            "extra_info": {
                "transaction_id": trxn.id,
            },
        }
    )


@csrf_exempt
def verify_razorpay_transaction(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    
    data = request.POST

    # Data from Razorpay Checkout
    payment_id = data.get("razorpay_payment_id")
    order_id = data.get("razorpay_order_id")
    signature = data.get("razorpay_signature")

    # Verify signature
    try:
        data_json = {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }
        if not rz_client.utility.verify_payment_signature(data_json):
            raise razorpay.errors.SignatureVerificationError("Signature verification failed")

        trxn = Transaction.objects.filter(
            json__razorpay_order_creation_data__id=order_id,
        ).first()
        if trxn:
            if trxn.credit(json=data_json):
                messages.success(request, "Payment successful")
            else:
                messages.error(request, "Failed to credit wallet")
        else:
            messages.error(request, "Transaction not found")
            
    except razorpay.errors.SignatureVerificationError:
        messages.error(request, "Payment verification failed")
    except Exception as e:
        mylogger.exception(f"Error verifying Razorpay transaction: {e}")

    return redirect("user_panel:dashboard")
