from decimal import Decimal

from django.test import TestCase

from account.models import User
from account.money import to_money
from wallet.models import Transaction


class ToMoneyTests(TestCase):
    def test_coerces_and_quantizes(self):
        self.assertEqual(to_money(0.1) + to_money(0.2), Decimal("0.30"))
        self.assertEqual(to_money("88.5"), Decimal("88.50"))
        self.assertEqual(to_money(100), Decimal("100.00"))
        self.assertEqual(to_money(None), Decimal("0.00"))
        self.assertEqual(to_money(2.005), Decimal("2.01"))  # half-up


class WalletDecimalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="dec@example.com", password="x", role="user"
        )
        self.user.balance = Decimal("1000.00")
        self.user.save(update_fields=["balance"])

    def _bal(self):
        return User.objects.get(pk=self.user.pk).balance

    def test_balance_is_decimal_after_reload(self):
        self.assertIsInstance(self._bal(), Decimal)

    def test_credit_debit_stay_exact_over_many_ops(self):
        for _ in range(30):
            self.assertTrue(self.user.credit(0.1))
            self.assertTrue(self.user.debit(0.1))
        self.assertEqual(self._bal(), Decimal("1000.00"))

    def test_create_transaction_stores_decimal(self):
        t = Transaction.create_transaction(
            self.user, merchant_txn_id="_t1", amount_rs=88.5,
            desc="shipping_charges", transaction_type="debit",
        )
        t.refresh_from_db()
        self.assertEqual(t.amount, Decimal("88.50"))

    def test_debit_records_decimal_closing_amount(self):
        t = Transaction.create_transaction(
            self.user, merchant_txn_id="_t2", amount_rs=120,
            desc="shipping_charges", transaction_type="debit",
        )
        self.assertTrue(t.debit())
        t.refresh_from_db()
        self.assertEqual(t.closing_amount, Decimal("880.00"))
        self.assertEqual(self._bal(), Decimal("880.00"))

    def test_min_balance_setter_negates_and_quantizes(self):
        self.user.min_balance = 500.5
        self.assertEqual(self.user._min_balance, Decimal("-500.50"))

    def test_have_balance_accepts_float(self):
        self.assertTrue(self.user.have_balance(999.99))
        self.assertFalse(self.user.have_balance(1000.01))
