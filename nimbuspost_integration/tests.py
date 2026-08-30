"""
Tests for the NimbusPost integration.

These stay at the HTTP boundary: ``requests`` is patched so nothing leaves the
machine, and the heavy Order object graph is only built where a test genuinely
needs it. Run with ``python manage.py test nimbuspost_integration``.
"""

import json
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from account import creds
from account.models import Courier
from nimbuspost_integration import nimbuspost
from nimbuspost_integration.constants import BASE_URL


def _resp(status_code=200, body=None, text=""):
    """Build a stand-in for ``requests.Response``."""
    r = mock.Mock()
    r.status_code = status_code
    r.url = "https://example.test"
    r.text = text or (json.dumps(body) if body is not None else "")
    if body is None:
        r.json.side_effect = ValueError("no json")
    else:
        r.json.return_value = body
    return r


class MapStatusTests(TestCase):
    def test_known_status_is_lowercased_and_trimmed(self):
        self.assertEqual(nimbuspost.map_status("  In Transit "), "in_transit")

    def test_unknown_status_returns_none(self):
        self.assertIsNone(nimbuspost.map_status("teleported"))

    def test_none_is_tolerated(self):
        self.assertIsNone(nimbuspost.map_status(None))


class SafeJsonTests(TestCase):
    def test_non_json_body_returns_empty_dict(self):
        self.assertEqual(nimbuspost._safe_json(_resp(body=None, text="<html>502</html>")), {})

    def test_list_body_is_wrapped(self):
        self.assertEqual(nimbuspost._safe_json(_resp(body=[1, 2])), {"data": [1, 2]})


@override_settings(
    NIMBUS_POST_URL="https://api.nimbuspost.test/v1/users/login",
    NIMBUS_API_EMAIL="a@b.com",
    NIMBUS_API_PASS="pw",
)
class GenerateTokenTests(TestCase):
    def setUp(self):
        creds.NIMBUSPOST_API_KEY = ""

    @mock.patch("nimbuspost_integration.nimbuspost.requests.post")
    def test_success_caches_token(self, post):
        post.return_value = _resp(body={"status": True, "data": "jwt-123"})
        self.assertTrue(nimbuspost.generate_token())
        self.assertEqual(creds.NIMBUSPOST_API_KEY, "jwt-123")

    @mock.patch("nimbuspost_integration.nimbuspost.requests.post")
    def test_rejected_login_returns_false(self, post):
        post.return_value = _resp(body={"status": False, "message": "bad creds"})
        self.assertFalse(nimbuspost.generate_token())
        self.assertEqual(creds.NIMBUSPOST_API_KEY, "")

    @override_settings(NIMBUS_API_EMAIL="", NIMBUS_API_PASS="")
    def test_missing_config_returns_false_without_calling_out(self):
        with mock.patch("nimbuspost_integration.nimbuspost.requests.post") as post:
            self.assertFalse(nimbuspost.generate_token())
            post.assert_not_called()


@override_settings(
    NIMBUS_POST_URL="https://api.nimbuspost.test/v1/users/login",
    NIMBUS_API_EMAIL="a@b.com",
    NIMBUS_API_PASS="pw",
)
class RequestRetryTests(TestCase):
    def setUp(self):
        creds.NIMBUSPOST_API_KEY = "stale-token"

    @mock.patch("nimbuspost_integration.nimbuspost.requests.post")
    @mock.patch("nimbuspost_integration.nimbuspost.requests.request")
    def test_expired_token_triggers_relogin_then_retry(self, request, post):
        request.side_effect = [
            _resp(status_code=401, body={"status": False, "message": "Invalid token"}),
            _resp(body={"status": True, "data": {"awb_number": "AWB1"}}),
        ]
        post.return_value = _resp(body={"status": True, "data": "fresh-token"})

        out = nimbuspost.nimbuspost_request("POST", "/shipments", {"x": 1})

        self.assertEqual(out.status_code, 200)
        self.assertEqual(request.call_count, 2)
        post.assert_called_once()
        self.assertEqual(creds.NIMBUSPOST_API_KEY, "fresh-token")

    @mock.patch("nimbuspost_integration.nimbuspost.requests.post")
    @mock.patch("nimbuspost_integration.nimbuspost.requests.request")
    def test_get_sends_params_not_body(self, request, post):
        request.return_value = _resp(body={"status": True, "data": {}})
        nimbuspost.track_shipment("AWB9")
        _, kwargs = request.call_args
        self.assertIsNone(kwargs["data"])
        self.assertEqual(request.call_args[0][1], f"{BASE_URL}/shipments/track/AWB9")


class ShipOrderTests(TestCase):
    @mock.patch("nimbuspost_integration.nimbuspost.order_booking")
    @mock.patch("nimbuspost_integration.nimbuspost.build_payload", return_value={"ok": 1})
    def test_network_error_is_structured_not_raised(self, _bp, booking):
        booking.side_effect = nimbuspost.requests.RequestException("boom")
        order = mock.Mock(id=1)
        ok, err = nimbuspost.ship_order(order, hub=mock.Mock())
        self.assertFalse(ok)
        self.assertIn("network error", err["error"])

    @mock.patch("nimbuspost_integration.nimbuspost.order_booking")
    @mock.patch("nimbuspost_integration.nimbuspost.build_payload", return_value={"ok": 1})
    def test_missing_awb_in_response_is_a_failure(self, _bp, booking):
        booking.return_value = _resp(body={"status": True, "data": {}})
        ok, err = nimbuspost.ship_order(mock.Mock(id=2), hub=mock.Mock())
        self.assertFalse(ok)
        self.assertIn("no AWB", err["error"])


@override_settings(NIMBUSPOST_WEBHOOK_SECRET="")
class WebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("nimbuspost_integration:webhook")

    def _post(self, payload):
        return self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

    def test_get_is_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_malformed_json_is_400(self):
        r = self.client.post(self.url, data="{not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_missing_fields_is_400(self):
        self.assertEqual(self._post({"awb_number": "A1"}).status_code, 400)

    def test_unknown_status_is_acked_not_errored(self):
        r = self._post({"awb_number": "A1", "status": "teleported"})
        self.assertEqual(r.status_code, 200)

    def test_known_status_but_no_order_is_404(self):
        Courier.objects.create(name="NimbusPost", abbreviation="nimbuspost")
        r = self._post({"awb_number": "does-not-exist", "status": "in transit"})
        self.assertEqual(r.status_code, 404)

    @override_settings(NIMBUSPOST_WEBHOOK_SECRET="s3cr3t")
    def test_signature_enforced_when_secret_set(self):
        r = self._post({"awb_number": "A1", "status": "in transit"})
        self.assertEqual(r.status_code, 401)
