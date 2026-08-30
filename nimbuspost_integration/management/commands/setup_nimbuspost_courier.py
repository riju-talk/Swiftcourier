"""
Create (or update) the Courier row that wires NimbusPost into the app.

The ship task and the webhook both look up ``Courier.objects.filter(
abbreviation="nimbuspost")`` and dispatch through ``integration_path``, so that
row has to exist for NimbusPost to do anything. This command is idempotent -
run it once per environment (or after a DB reset).

    python manage.py setup_nimbuspost_courier
"""

from django.core.management.base import BaseCommand

from account.models import Courier

ABBREVIATION = "nimbuspost"
INTEGRATION_PATH = "nimbuspost_integration.nimbuspost"


class Command(BaseCommand):
    help = "Create or update the NimbusPost Courier row."

    def handle(self, *args, **options):
        courier, created = Courier.objects.update_or_create(
            abbreviation=ABBREVIATION,
            defaults={
                "name": "NimbusPost",
                "integration_path": INTEGRATION_PATH,
                "website": "https://nimbuspost.com/",
                "_base_tracking_url": "https://ship.nimbuspost.com/shipment/tracking/{tracking_id}",
                "active": True,
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} Courier #{courier.id} ({courier.name}, {ABBREVIATION}).")
        )
