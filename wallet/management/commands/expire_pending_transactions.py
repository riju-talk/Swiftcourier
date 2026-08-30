"""Fail off wallet transactions that were created but never completed.

``Transaction.create_transaction()`` writes a ``PENDING`` row; if ``.credit()`` /
``.debit()`` is never reached (a payment the user abandoned, a ship task that
died before charging, a crash between create and debit) the row lingers forever.
PENDING never touches ``User.balance``, but it pollutes every ``sum(amount)``
report and makes the ledger hard to read.

A real in-flight payment session times out in minutes, so anything PENDING for
more than ``--hours`` (default 6) is dead. Mark it FAILED.

    uv run manage.py expire_pending_transactions            # default 6h
    uv run manage.py expire_pending_transactions --hours 2 --dry-run
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from wallet.models import Transaction


class Command(BaseCommand):
    help = "Mark long-stale PENDING wallet transactions as FAILED."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=6)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        cutoff = now() - timedelta(hours=opts["hours"])
        stale = Transaction.objects.filter(status="PENDING", created_at__lt=cutoff)
        n = stale.count()

        if opts["dry_run"]:
            by_type = {}
            for t in stale.values_list("transaction_type", flat=True):
                by_type[t] = by_type.get(t, 0) + 1
            self.stdout.write(f"would expire {n} PENDING txn(s) older than "
                              f"{opts['hours']}h: {by_type}")
            return

        updated = stale.update(status="FAILED", updated_at=now())
        self.stdout.write(
            self.style.SUCCESS(f"expired {updated} stale PENDING transaction(s)")
        )
