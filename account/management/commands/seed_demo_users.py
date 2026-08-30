"""
Idempotent demo/test accounts for a client walkthrough.

    python manage.py seed_demo_users

Creates a merchant, an ops admin and a super admin, each with KYC pre-approved
and the agreement pre-accepted so they log straight in with no gates. The
merchant gets a funded wallet and a primary warehouse so every panel is
explorable end to end.

Passwords come from env (DEMO_MERCHANT_PASSWORD / DEMO_ADMIN_PASSWORD /
DEMO_SUPERADMIN_PASSWORD) and fall back to the values printed at the end.
"""

import os

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now

from account.models import User


DEMO = [
    {
        "email": "merchant@swiftcourier.app",
        "password": os.getenv("DEMO_MERCHANT_PASSWORD", "Merchant@2026"),
        "role": "user",
        "full_name": "Demo Merchant",
        "company_name": "Demo Logistics Pvt Ltd",
        "balance": 50000,
    },
    {
        "email": "ops@swiftcourier.app",
        "password": os.getenv("DEMO_ADMIN_PASSWORD", "Ops@2026"),
        "role": "admin",
        "full_name": "Ops Admin",
        "company_name": "",
        "balance": 0,
    },
    {
        "email": "admin@swiftcourier.app",
        "password": os.getenv("DEMO_SUPERADMIN_PASSWORD", "SuperAdmin@2026"),
        "role": "super_admin",
        "full_name": "SwiftCourier Admin",
        "company_name": "",
        "balance": 0,
    },
]


class Command(BaseCommand):
    help = "Create/refresh demo accounts (KYC approved, agreement accepted, funded)."

    @transaction.atomic
    def handle(self, *args, **options):
        for spec in DEMO:
            user, created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "full_name": spec["full_name"],
                    "company_name": spec["company_name"],
                    "role": spec["role"],
                },
            )
            user.role = spec["role"]
            user.full_name = spec["full_name"]
            user.company_name = spec["company_name"]
            user.is_active = True
            user._status = "active"
            if spec["role"] == "super_admin":
                user.is_staff = user.is_superuser = True
            elif spec["role"] == "admin":
                user.is_staff = True
            user.set_password(spec["password"])
            user.save()

            if spec["balance"]:
                user.balance = spec["balance"]
                user.save(update_fields=["balance"])

            # KYC: approved + agreement accepted -> no login gate, no popup
            kyc = user.get_kyc()
            kyc._status = "approved"
            kyc._is_agreement_accepted = True
            kyc.kyc_form_submitted_at = kyc.kyc_form_submitted_at or now()
            kyc.approved_by = "seed_demo_users"
            kyc.save()

            # merchant: a primary warehouse so Add Order / labels work
            if spec["role"] == "user":
                self._ensure_primary_hub(user)

            verb = "created" if created else "updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {verb:8} {spec['email']:28} role={spec['role']:12} "
                    f"kyc=approved balance={spec['balance']}"
                )
            )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Demo credentials"))
        for spec in DEMO:
            self.stdout.write(f"  {spec['email']:28}  {spec['password']}")

    def _ensure_primary_hub(self, user):
        from order_manager.models import Hub

        if Hub.objects.filter(user=user, is_active=True).exists():
            return
        Hub.objects.create(
            user=user,
            name="Main Warehouse",
            contact_person="Demo Merchant",
            address_line1="221B Baker Street",
            city="New Delhi",
            state="Delhi",
            pin_code="110001",
            country="India",
            phone="9876543210",
            email=user.email,
            is_primary=True,
            is_active=True,
        )
        self.stdout.write("           + primary warehouse 'Main Warehouse'")
