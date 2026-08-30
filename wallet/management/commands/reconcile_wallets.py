"""Read-only wallet ledger audit.

For every user it walks the ``SUCCESS`` transaction ledger in chronological order
and checks three things:

1. the ``closing_amount`` snapshot on each row moves by exactly ``±amount`` from
   the previous row (the ledger is internally consistent);
2. the last ``closing_amount`` equals the user's stored ``balance``;
3. no ``PENDING`` transactions are older than ``--stale-days`` (default 2).

Nothing is written. Use it before/after the Float->Decimal migration and as a
periodic prod health check.

    uv run manage.py reconcile_wallets
    uv run manage.py reconcile_wallets --user user@user.com --verbose
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta

from account.models import User
from account.money import to_money

TOL = Decimal("0.01")


class Command(BaseCommand):
    help = "Audit wallet ledgers for internal consistency (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Limit to a single user email.")
        parser.add_argument("--stale-days", type=int, default=2)
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **opts):
        users = User.objects.all().order_by("id")
        if opts["user"]:
            users = users.filter(email=opts["user"])

        stale_before = now() - timedelta(days=opts["stale_days"])
        total_bad = 0
        total_checked = 0

        for user in users:
            txns = list(
                user.transactions.filter(status="SUCCESS").order_by("created_at", "id")
            )
            pending = user.transactions.filter(
                status="PENDING", created_at__lt=stale_before
            ).count()
            total_checked += 1

            problems = []
            running = None
            for t in txns:
                amt = to_money(t.amount)
                signed = amt if t.transaction_type == "credit" else -amt
                if running is not None:
                    expected = to_money(running + signed)
                    if abs(to_money(t.closing_amount) - expected) > TOL:
                        problems.append(
                            f"  txn #{t.id} {t.created_at:%Y-%m-%d} {t.transaction_type} "
                            f"{amt}: closing={t.closing_amount} expected~{expected}"
                        )
                running = to_money(t.closing_amount)

            stored = to_money(user.balance)
            if running is not None and abs(running - stored) > TOL:
                problems.append(
                    f"  ledger tail {running} != stored balance {stored} "
                    f"(delta {to_money(stored - running)})"
                )

            if problems or pending:
                total_bad += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"\n{user.email} (id={user.id}, role={user.role}) "
                        f"balance={stored} txns={len(txns)}"
                    )
                )
                if pending:
                    self.stdout.write(f"  {pending} PENDING txn(s) older than "
                                      f"{opts['stale_days']}d")
                for p in problems:
                    self.stdout.write(p)
            elif opts["verbose"]:
                self.stdout.write(self.style.SUCCESS(
                    f"{user.email}: OK ({len(txns)} txns, balance {stored})"
                ))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nchecked {total_checked} user(s); {total_bad} with findings"
            )
            if not total_bad
            else self.style.ERROR(
                f"\nchecked {total_checked} user(s); {total_bad} with findings"
            )
        )
