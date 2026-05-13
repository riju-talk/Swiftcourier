import pandas as pd
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware, now
from django.db import transaction

from ...models import Order, Shipment


class Command(BaseCommand):
    help = "Update order status with strict validation (status + date)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="Path to Excel file",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Skip all validation and force-update status as-is",
        )

    def parse_datetime(self, value, field_name, awb, errors):
        if pd.isna(value) or value == "":
            return None

        if isinstance(value, datetime):
            dt = make_aware(value)
        else:
            try:
                dt = make_aware(pd.to_datetime(value))
            except Exception:
                errors.append(f"AWB: {awb} | Invalid {field_name}: {value}")
                return None

        # ✅ FUTURE DATE CHECK
        if dt > now():
            errors.append(f"AWB: {awb} | {field_name} cannot be in future: {value}")
            return None

        return dt

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = options["file"]
        force = options["force"]

        self.stdout.write(f"Reading file: {file_path}")

        if force:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  --force mode: skipping all validation, updating status as-is"
                )
            )

        df = pd.read_excel(file_path)
        df = df.fillna("")

        required_columns = [
            "AWB Number",
            "New Status",
            "Delivered At",
            "RTO At",
            "RTO Delivered At",
        ]

        for col in required_columns:
            if col not in df.columns:
                self.stdout.write(self.style.ERROR(f"Missing column: {col}"))
                return

        awb_list = df["AWB Number"].astype(str).str.strip().tolist()

        orders = Order.objects.select_related("shipment").filter(
            awb_number__in=awb_list
        )

        order_map = {str(o.awb_number): o for o in orders}

        order_updates = []
        shipment_updates = []
        errors = []
        not_found = 0

        if not force:
            # ✅ VALID STATUS SET
            valid_statuses = set(Order.ORDER_MAPPING.keys())

            # 🚨 STEP 1: VALIDATE ALL STATUSES FIRST (FAIL FAST)
            invalid_status_rows = []

            for _, row in df.iterrows():
                awb = str(row["AWB Number"]).strip()
                status = str(row["New Status"]).strip().lower()

                if status and status not in valid_statuses:
                    invalid_status_rows.append(f"AWB: {awb} | Invalid status: {status}")

            if invalid_status_rows:
                self.stdout.write(self.style.ERROR("\n❌ Invalid Status Found:"))
                for err in invalid_status_rows:
                    self.stdout.write(self.style.ERROR(err))

                self.stdout.write(self.style.ERROR("\n🚫 Aborting entire process"))
                return  # ❌ STOP EVERYTHING

        # 🚀 STEP 2: PROCESS DATA
        for _, row in df.iterrows():
            awb = str(row["AWB Number"]).strip()

            if awb not in order_map:
                not_found += 1
                continue

            order = order_map[awb]
            shipment = getattr(order, "shipment", None)

            new_status = str(row["New Status"]).strip().lower()

            order_updated = False
            shipment_updated = False

            if force:
                # ⚡ FORCE MODE: just slam the status in, no questions asked
                if new_status:
                    order.status = new_status
                    order_updated = True
            else:
                old_status = (order.status or "").lower()

                delivered_at = self.parse_datetime(
                    row["Delivered At"], "Delivered At", awb, errors
                )
                rto_at = self.parse_datetime(row["RTO At"], "RTO At", awb, errors)
                rto_delivered_at = self.parse_datetime(
                    row["RTO Delivered At"], "RTO Delivered At", awb, errors
                )

                # ✅ STATUS UPDATE ONLY IF DIFFERENT
                if new_status and new_status != old_status:
                    order.status = new_status
                    order_updated = True

                # ✅ SHIPMENT LOGIC (only fill missing)
                if shipment:
                    if delivered_at and not shipment.delivered_at:
                        shipment.delivered_at = delivered_at
                        shipment_updated = True

                    if rto_at and not shipment.rto_at:
                        shipment.rto_at = rto_at
                        shipment_updated = True

                    if rto_delivered_at and not shipment.rto_delivered_at:
                        shipment.rto_delivered_at = rto_delivered_at
                        shipment_updated = True

            if order_updated:
                order_updates.append(order)

            if shipment_updated:
                shipment_updates.append(shipment)

        # 🚀 BULK UPDATE
        if order_updates:
            Order.objects.bulk_update(order_updates, ["status"], batch_size=1000)

        if shipment_updates:
            Shipment.objects.bulk_update(
                shipment_updates,
                ["delivered_at", "rto_at", "rto_delivered_at"],
                batch_size=1000,
            )

        # 📊 OUTPUT
        self.stdout.write(self.style.SUCCESS(f"✅ Updated {len(order_updates)} orders"))
        self.stdout.write(
            self.style.SUCCESS(f"✅ Updated {len(shipment_updates)} shipments")
        )
        self.stdout.write(self.style.WARNING(f"⚠️ AWBs not found: {not_found}"))

        # 🚨 DATE ERRORS (only relevant in normal mode)
        if not force:
            if errors:
                self.stdout.write(self.style.ERROR("\n❌ Date Errors:"))
                for err in errors:
                    self.stdout.write(self.style.ERROR(err))
            else:
                self.stdout.write(self.style.SUCCESS("🎉 No date errors found"))
