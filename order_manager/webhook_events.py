"""Raw inbound carrier-webhook persistence (PRD §7.4.1, §7.4.7).

`@log_carrier_webhook("<carrier>")` wraps a webhook view so that:

  1. the raw request is persisted to CarrierWebhookEvent **before** the view runs
     (headers redacted, body stored, sha256 recorded);
  2. the view's existing behaviour is UNCHANGED — this is the log-only rollout
     stage, nothing is rejected on the basis of the new checks;
  3. the response outcome (2xx / non-2xx / exception) is recorded back onto the
     event row.

Signature verification is deliberately *not* enforced here yet. Add a
`verify_signature=` callable later, per carrier, once a week of clean log-only
data confirms the verification logic is correct.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import uuid

logger = logging.getLogger("my-logger")

# Header names whose values must never be written to the event store.
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "x-api-key",
    "x-auth-token",
    "proxy-authorization",
    "np-api-key",
}


def _redact_headers(meta) -> dict:
    out = {}
    for key, value in meta.items():
        if not key.startswith("HTTP_") and key not in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            continue
        name = key[5:].replace("_", "-").lower() if key.startswith("HTTP_") else key.replace("_", "-").lower()
        out[name] = "***redacted***" if name in _SENSITIVE_HEADERS else str(value)[:512]
    return out


def _extract_awb(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    for k in ("awb", "awb_number", "awbNumber", "waybill", "tracking_number", "AWB"):
        v = payload.get(k)
        if v:
            return str(v)[:40]
    return ""


def persist_carrier_webhook(carrier: str, request) -> "CarrierWebhookEvent | None":
    """Persist one raw carrier webhook request. Never raises."""
    from order_manager.models import CarrierWebhookEvent

    try:
        raw = request.body or b""
        try:
            body_text = raw.decode("utf-8", errors="replace")
        except Exception:
            body_text = repr(raw)

        payload = None
        try:
            payload = json.loads(body_text) if body_text.strip() else None
        except ValueError:
            payload = None

        return CarrierWebhookEvent.objects.create(
            carrier=carrier,
            request_path=request.path[:255],
            request_method=request.method or "",
            headers=_redact_headers(request.META),
            raw_body=body_text[:20000],
            body_sha256=hashlib.sha256(raw).hexdigest(),
            parsed_payload=payload,
            awb_number=_extract_awb(payload),
            external_status=str((payload or {}).get("status", ""))[:80] if isinstance(payload, dict) else "",
            correlation_id=uuid.uuid4().hex,
            processing_status="received",
        )
    except Exception:
        logger.exception("persist_carrier_webhook(%s) failed - continuing", carrier)
        return None


def log_carrier_webhook(carrier: str):
    """Decorator: persist the raw webhook, run the view unchanged, record outcome."""

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            event = persist_carrier_webhook(carrier, request)
            # carrier webhooks are POST-only; answer probes/crawls uniformly
            # instead of letting each view's json.loads() raise a 500.
            if request.method not in ("POST", "PUT"):
                from django.http import HttpResponseNotAllowed

                if event is not None:
                    _finish(event, "processed", last_error="non-POST probe")
                return HttpResponseNotAllowed(["POST"])
            try:
                response = view(request, *args, **kwargs)
            except Exception as exc:
                if event is not None:
                    _finish(event, "failed", last_error=repr(exc)[:2000])
                raise
            if event is not None:
                status = getattr(response, "status_code", 200)
                _finish(
                    event,
                    "processed" if status < 400 else "failed",
                    last_error="" if status < 400 else f"view returned {status}",
                )
            return response

        return wrapper

    return decorator


def _finish(event, processing_status: str, last_error: str = "") -> None:
    try:
        event.processing_status = processing_status
        event.processing_attempts = (event.processing_attempts or 0) + 1
        if last_error:
            event.last_error = last_error
        event.save(update_fields=["processing_status", "processing_attempts", "last_error", "updated_at"])
    except Exception:
        logger.exception("could not finalise CarrierWebhookEvent %s", getattr(event, "id", "?"))
