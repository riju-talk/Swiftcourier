"""
Quick local testing tool for courier webhook integrations.

Fires a synthetic webhook payload straight through Django's test client
(no running server, no real courier needed) at any integration's webhook
view, and prints back the exact status code + body it returned. Meant for
exercising the error-handling paths added across every *_integration app
(missing fields, unknown status, order-not-found, malformed JSON, etc.)
without waiting on a real courier callback.

Examples:
    # See every integration this knows about, its URL, and payload shape
    python manage.py test_webhook --list

    # Minimal smoke test with an auto-built payload (a placeholder AWB and
    # a representative "known" status for that integration)
    python manage.py test_webhook xpressbees

    # Target a real order + a specific raw courier status string/code
    python manage.py test_webhook shiprocket --awb 1234567890 --status DELIVERED

    # Full manual control over the payload
    python manage.py test_webhook nimbuspost --payload '{"awb": "AWB1", "status": "in_transit"}'
    python manage.py test_webhook nimbuspost --payload-file sample.json
"""

import hashlib
import hmac
import base64
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse


# One entry per courier integration app. `shape` controls how --awb/--status
# get assembled into a payload when --payload/--payload-file aren't given:
#   "flat"           -> {<awb_field>: awb, <status_field>: status}
#   "nested_data"     -> {"data": {<awb_field>: awb, <status_field>: status}}
#   "nested_records"  -> RapidShyp's {"records": [{"shipment_details": [...]}]}
INTEGRATIONS = {
    "xpressbees": {
        "url": "xpressbees_integration:webhook",
        "shape": "flat",
        "awb_field": "awb_number",
        "status_field": "status_code",
        "sample_status": "IT",
        "secret_setting": "SECRET_KEY",
    },
    "lastmiles": {
        "url": "lastmiles_integration:webhook",
        "shape": "flat",
        "awb_field": "awb_number",
        "status_field": "status",
        "sample_status": None,  # TODO in views.py: not implemented yet
        "note": "webhook is a stub (logs + acks only) - no real payload observed yet",
    },
    "purple_drone": {
        "url": "purpledrone_integration:webhook",
        "shape": "nested_data",
        "awb_field": "tracking_number",
        "status_field": "status",
        "sample_status": "O-PICKEDUP",
    },
    "parcelx": {
        "url": "parcelx_integration:webhook",
        "shape": "flat",
        "awb_field": "awb",
        "status_field": "status_title",
        "sample_status": "Delivered",
    },
    "shiprocket": {
        "url": "shiprocket_integration:webhook",
        "shape": "flat",
        "awb_field": "awb",
        "status_field": "current_status",
        "sample_status": "DELIVERED",
    },
    "jiffy": {
        "url": "jiffy_integration:webhook",
        "shape": "flat",
        "awb_field": "awb_number",
        "status_field": "status",
        "sample_status": "delivered",
    },
    "fship": {
        "url": "fship_integration:webhook",
        "shape": "flat",
        "awb_field": "awb",
        "status_field": "status",
        "sample_status": "Delivered",
    },
    "rapidshyp": {
        "url": "rapidshyp_integration:rapidshyp_webhook",
        "shape": "nested_records",
        "awb_field": "awb",
        "status_field": "current_tracking_status_code",
        "sample_status": "DEL",
    },
    "rapidshyp_new": {
        "url": "rapidshyp_new_integration:rapidshyp_new_webhook",
        "shape": "nested_records",
        "awb_field": "awb",
        "status_field": "current_tracking_status_code",
        "sample_status": "DEL",
    },
    "smartship": {
        "url": "smartship_integration:webhook",
        "shape": "flat",
        "awb_field": "awbno",
        "status_field": "status",
        "sample_status": 11,
    },
    "bdl": {
        "url": "bdl_integration:webhook",
        "shape": "flat",
        "awb_field": "awb_number",
        "status_field": "status",
        "sample_status": None,  # TODO in views.py: not implemented yet
        "note": "webhook is a stub (logs + acks only) - no real payload observed yet",
    },
    "zippyy": {
        "url": "zippyy_integration:webhook",
        "shape": "flat",
        "awb_field": "awb_number",
        "status_field": "status",
        "sample_status": None,  # TODO in views.py: not implemented yet
        "note": "webhook is a stub (logs + acks only) - no real payload observed yet",
    },
    "tci_express": {
        "url": "tci_express_integration:webhook",
        "shape": "flat",
        "awb_field": "awb",
        "status_field": "status",
        "sample_status": "Delivered",
        "note": "app isn't registered in INSTALLED_APPS/urls.py yet - URL won't resolve",
    },
    "nimbuspost": {
        "url": "nimbuspost_integration:webhook",
        "shape": "flat",
        "awb_field": "awb_number",
        "status_field": "status",
        "sample_status": "in transit",
        "secret_setting": "NIMBUSPOST_WEBHOOK_SECRET",
        "note": "schema confirmed from NimbusPost's dashboard docs, but only "
        "'in transit' is a confirmed real status value - the rest of "
        "STATUS_MAPPING is a best-effort guess, see constants.py",
    },
}


def build_payload(config, awb, status):
    awb_field = config["awb_field"]
    status_field = config["status_field"]
    shape = config["shape"]

    if shape == "flat":
        return {awb_field: awb, status_field: status}
    if shape == "nested_data":
        return {"data": {awb_field: awb, status_field: status}}
    if shape == "nested_records":
        return {
            "records": [
                {"shipment_details": [{awb_field: awb, status_field: status}]}
            ]
        }
    raise ValueError(f"Unknown payload shape: {shape}")


class Command(BaseCommand):
    help = "Fire a synthetic webhook payload at a courier integration's webhook view (no real courier or running server needed)."

    def add_arguments(self, parser):
        parser.add_argument(
            "integration",
            nargs="?",
            choices=sorted(INTEGRATIONS.keys()),
            help="Which integration's webhook to call.",
        )
        parser.add_argument("--list", action="store_true", help="List all known integrations and exit.")
        parser.add_argument("--awb", default="TEST0000000001", help="AWB/tracking number to embed (default: a placeholder).")
        parser.add_argument("--status", default=None, help="Raw courier status value to embed (default: a known-mapped sample status for that integration).")
        parser.add_argument("--payload", default=None, help="Raw JSON string to POST verbatim, overriding --awb/--status.")
        parser.add_argument("--payload-file", default=None, help="Path to a JSON file to POST verbatim, overriding --awb/--status.")

    def handle(self, *args, **options):
        if options["list"] or not options["integration"]:
            self._print_list()
            return

        config = INTEGRATIONS[options["integration"]]

        if options["payload_file"]:
            with open(options["payload_file"], "r", encoding="utf-8") as f:
                body = f.read()
        elif options["payload"]:
            body = options["payload"]
        else:
            status = options["status"] if options["status"] is not None else config["sample_status"]
            if status is None:
                raise CommandError(
                    f"'{options['integration']}' has no known sample status (its webhook is "
                    "unverified/not implemented yet) - pass --status or --payload explicitly."
                )
            body = json.dumps(build_payload(config, options["awb"], status))

        try:
            url = reverse(config["url"])
        except Exception as e:
            raise CommandError(f"Could not resolve URL '{config['url']}': {e}")

        headers = {}
        secret = getattr(settings, config.get("secret_setting", ""), None)
        if secret:
            headers["HTTP_X_HMAC_SHA256"] = base64.b64encode(
                hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
            ).decode()

        self.stdout.write(f"POST {url}")
        self.stdout.write(f"body: {body}")

        # Client() defaults to Host: testserver, which isn't in ALLOWED_HOSTS
        # outside of an actual `manage.py test` run - pin it to a host that is.
        # A bare "*" in ALLOWED_HOSTS means allow-all but is not itself a valid
        # Host header (fails RFC 1034/1035), so fall back to localhost then.
        allowed = [h for h in settings.ALLOWED_HOSTS if h not in ("*", "")]
        client = Client(SERVER_NAME=(allowed or ["127.0.0.1"])[0])
        response = client.post(url, data=body, content_type="application/json", **headers)

        style = self.style.SUCCESS if response.status_code < 400 else self.style.ERROR
        self.stdout.write(style(f"-> {response.status_code}"))
        try:
            self.stdout.write(json.dumps(response.json(), indent=2))
        except (ValueError, AttributeError):
            self.stdout.write(response.content.decode("utf-8", errors="replace"))

    def _print_list(self):
        for name, config in sorted(INTEGRATIONS.items()):
            self.stdout.write(self.style.MIGRATE_HEADING(name))
            self.stdout.write(f"  url:    {config['url']}")
            self.stdout.write(f"  shape:  {config['shape']} (awb field={config['awb_field']!r}, status field={config['status_field']!r})")
            secret_setting = config.get("secret_setting")
            if secret_setting:
                configured = "configured" if getattr(settings, secret_setting, None) else "NOT configured"
                self.stdout.write(
                    f"  auth:   signs X-Hmac-Sha256 from settings.{secret_setting} if set "
                    f"(currently {configured}); computed automatically by this command"
                )
            if config["sample_status"] is not None:
                self.stdout.write(f"  sample status: {config['sample_status']!r}")
            if config.get("note"):
                self.stdout.write(self.style.WARNING(f"  note:   {config['note']}"))
            self.stdout.write("")
