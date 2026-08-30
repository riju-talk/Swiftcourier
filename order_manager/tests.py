from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils.timezone import now

from account.models import Courier, RateCard, User
from order_manager.models import Hub, Order
from wallet.models import Transaction


class WalletNonPositiveGuardTests(TestCase):
    """credit/debit and the shipping charge/refund helpers must reject <= 0
    amounts - a negative would move the balance the wrong way."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="np@example.com", password="x", role="user"
        )
        self.user.balance = 100
        self.user.save(update_fields=["balance"])
        self.order = Order.objects.create(user=self.user, awb_number="AWB-NP")
        from order_manager.models import Payment
        Payment.objects.create(order=self.order, amount=0, shipping_charges=-50)

    def _bal(self):
        return User.objects.get(pk=self.user.pk).balance

    def test_credit_rejects_zero_and_negative(self):
        self.assertFalse(self.user.credit(0))
        self.assertFalse(self.user.credit(-10))
        self.assertEqual(self._bal(), 100)

    def test_debit_rejects_negative(self):
        self.assertFalse(self.user.debit(-10))
        self.assertEqual(self._bal(), 100)

    def test_charge_shipping_rejects_negative(self):
        self.assertIsNone(self.order.charge_shipping(-25))
        self.assertEqual(self._bal(), 100)

    def test_refund_shipping_rejects_negative(self):
        # payment.shipping_charges is -50
        self.assertIsNone(self.order.refund_shipping())
        self.assertEqual(self._bal(), 100)


class UpdateStatusEdgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="us@example.com", password="x", role="user"
        )

    def test_same_status_is_noop(self):
        o = Order.objects.create(user=self.user, status="in_transit", awb_number="A")
        before = o.updated_at
        self.assertTrue(o.update_status("in_transit"))
        o.refresh_from_db()
        self.assertEqual(o.updated_at, before)  # nothing written

    def test_status_change_without_shipment_does_not_crash(self):
        o = Order.objects.create(user=self.user, awb_number="A2")
        # no Shipment row
        self.assertTrue(o.update_status("in_transit"))
        o.refresh_from_db()
        self.assertEqual(o.status, "in_transit")

    def test_status_change_bumps_updated_at(self):
        o = Order.objects.create(user=self.user, awb_number="A3")
        Order.objects.filter(pk=o.pk).update(updated_at=now() - timedelta(hours=1))
        o.refresh_from_db()
        old = o.updated_at
        o.update_status("processing")
        o.refresh_from_db()
        self.assertGreater(o.updated_at, old)


class ReclaimDoesNotYankShippedOrders(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="ry@example.com", password="x", role="user"
        )

    def test_awb_set_order_is_left_alone(self):
        o = Order.objects.create(user=self.user, status="processing", awb_number="AWB-99")
        Order.objects.filter(pk=o.pk).update(updated_at=now() - timedelta(hours=2))
        self.assertEqual(Order.reclaim_stuck_processing(self.user), 0)
        o.refresh_from_db()
        self.assertEqual(o.status, "processing")

    def test_charged_order_is_left_alone(self):
        o = Order.objects.create(user=self.user, status="processing", awb_number="")
        Order.objects.filter(pk=o.pk).update(updated_at=now() - timedelta(hours=2))
        Transaction.objects.create(
            user=self.user, transaction_type="debit", amount=88, status="SUCCESS",
            desc="shipping_charges",
            merchant_transaction_id=f"{self.user.id}_shipping_charges_{o.id}_noawb",
        )
        self.assertEqual(Order.reclaim_stuck_processing(self.user), 0)
        o.refresh_from_db()
        self.assertEqual(o.status, "processing")

    def test_genuinely_stuck_order_is_reclaimed(self):
        o = Order.objects.create(user=self.user, status="processing", awb_number="")
        Order.objects.filter(pk=o.pk).update(updated_at=now() - timedelta(hours=2))
        self.assertEqual(Order.reclaim_stuck_processing(self.user), 1)
        o.refresh_from_db()
        self.assertEqual(o.status, "ready_to_ship")


class CancelOrderHonestyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="co@example.com", password="pw", role="user"
        )
        self.client.force_login(self.user)

    def test_cancel_of_in_transit_order_is_rejected_not_faked(self):
        o = Order.objects.create(user=self.user, status="in_transit", awb_number="A")
        r = self.client.get(f"/order/cancel-order/{o.id}/", follow=True)
        o.refresh_from_db()
        self.assertEqual(o.status, "in_transit")  # unchanged
        msgs = [str(m) for m in list(r.context["messages"])]
        self.assertTrue(any("can't be" in m for m in msgs))

    def test_cancel_of_ready_to_ship_still_works(self):
        o = Order.objects.create(user=self.user, status="ready_to_ship", awb_number="")
        self.client.get(f"/order/cancel-order/{o.id}/", follow=True)
        o.refresh_from_db()
        self.assertEqual(o.status, "cancelled")


class ExpirePendingTransactionsTests(TestCase):
    def test_only_old_pending_are_failed(self):
        from django.core.management import call_command
        from io import StringIO

        u = User.objects.create_user(email="ep@example.com", password="x", role="user")
        old = Transaction.objects.create(
            user=u, transaction_type="credit", amount=100, status="PENDING",
            merchant_transaction_id="ep-old",
        )
        Transaction.objects.filter(pk=old.pk).update(
            created_at=now() - timedelta(hours=12)
        )
        fresh = Transaction.objects.create(
            user=u, transaction_type="credit", amount=100, status="PENDING",
            merchant_transaction_id="ep-fresh",
        )
        done = Transaction.objects.create(
            user=u, transaction_type="credit", amount=100, status="SUCCESS",
            merchant_transaction_id="ep-done",
        )
        Transaction.objects.filter(pk=done.pk).update(
            created_at=now() - timedelta(hours=12)
        )
        call_command("expire_pending_transactions", stdout=StringIO())
        old.refresh_from_db(); fresh.refresh_from_db(); done.refresh_from_db()
        self.assertEqual(old.status, "FAILED")
        self.assertEqual(fresh.status, "PENDING")
        self.assertEqual(done.status, "SUCCESS")


class ShipOrderBrokerDownTests(TestCase):
    """If the celery broker is unreachable, Ship must not 500 and must not
    strand the orders in `processing`."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="ship-broker@example.com", password="pw", role="user"
        )
        self.client.force_login(self.user)
        self.hub = Hub.objects.create(
            name="BrokerHub", address_line1="1 Test Street", city="Delhi",
            state="Delhi", country="India", pin_code="110075", phone="9090909090",
            user=self.user,
        )
        self.courier = Courier.objects.create(name="TestCourier", abbreviation="TC")
        self.rate_card = RateCard.objects.create(user=self.user, courier=self.courier)
        self.order = Order.objects.create(user=self.user, awb_number="")

    def test_broker_failure_rolls_back_to_ready_to_ship(self):
        with mock.patch(
            "order_manager.views.group"
        ) as m_group:
            m_group.return_value.apply_async.side_effect = OSError("broker down")
            r = self.client.post(
                "/order/ship-order/",
                {"order_ids": str(self.order.id), "warehouse": str(self.hub.id),
                 "courier": str(self.courier.id)},
                follow=True,
            )
        self.assertEqual(r.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "ready_to_ship")


class ProcessingReclaimTests(TestCase):
    """Orders must not get stranded in `processing` if the async ship task dies."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="proc-test@example.com", password="x", role="user"
        )

    def test_send_to_processing_only_takes_ready_orders(self):
        o1 = Order.objects.create(user=self.user, awb_number="A1")  # ready_to_ship
        o2 = Order.objects.create(user=self.user, awb_number="A2", status="delivered")
        ready, failed = Order.send_to_processing([o1.id, o2.id], self.user)
        self.assertEqual(ready, [o1.id])
        self.assertEqual(failed, [o2.id])
        self.assertEqual(Order.objects.get(pk=o1.id).status, "processing")

    def test_fresh_processing_orders_are_left_alone(self):
        o = Order.objects.create(user=self.user, awb_number="")
        Order.send_to_processing([o.id], self.user)
        self.assertEqual(Order.reclaim_stuck_processing(self.user), 0)
        self.assertEqual(Order.objects.get(pk=o.id).status, "processing")

    def test_stale_processing_orders_are_reclaimed(self):
        # genuinely stuck: no AWB (carrier never booked it), no charge
        o = Order.objects.create(user=self.user, awb_number="")
        Order.send_to_processing([o.id], self.user)
        Order.objects.filter(pk=o.id).update(updated_at=now() - timedelta(minutes=45))
        self.assertEqual(Order.reclaim_stuck_processing(self.user), 1)
        self.assertEqual(Order.objects.get(pk=o.id).status, "ready_to_ship")


class ChargeShippingIdempotencyTests(TestCase):
    """Order.charge_shipping must debit the wallet once per AWB, no matter how
    many times a retried task / double-clicked button calls it."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="ship-test@example.com", password="x", role="user"
        )
        self.user.balance = 1000.0
        self.user.save(update_fields=["balance"])
        self.order = Order.objects.create(user=self.user, awb_number="AWB-100")

    def _balance(self):
        return User.objects.get(pk=self.user.pk).balance

    def test_single_charge(self):
        trxn = self.order.charge_shipping(120.0)
        self.assertIsNotNone(trxn)
        self.assertEqual(trxn.status, "SUCCESS")
        self.assertEqual(self._balance(), 880.0)

    def test_retry_does_not_double_charge(self):
        t1 = self.order.charge_shipping(120.0)
        t2 = self.order.charge_shipping(120.0)
        t3 = self.order.charge_shipping(120.0)
        self.assertEqual(t1.id, t2.id)
        self.assertEqual(t1.id, t3.id)
        self.assertEqual(self._balance(), 880.0)
        self.assertEqual(
            Transaction.objects.filter(
                user=self.user, desc="shipping_charges"
            ).count(),
            1,
        )

    def test_reship_after_new_awb_charges_again(self):
        self.order.charge_shipping(120.0)
        self.order.awb_number = "AWB-200"  # fresh AWB = new ship attempt
        self.order.save(update_fields=["awb_number"])
        self.order.charge_shipping(90.0)
        self.assertEqual(self._balance(), 790.0)
        self.assertEqual(
            Transaction.objects.filter(
                user=self.user, desc="shipping_charges"
            ).count(),
            2,
        )

    def test_insufficient_balance_returns_none(self):
        self.assertIsNone(self.order.charge_shipping(5000.0))
        self.assertEqual(self._balance(), 1000.0)


class InvoiceSummaryTests(TestCase):
    """Order.invoice_summary() must reconcile to grand_total and not show the
    total amount in the tax row."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="inv@example.com", password="x", role="user"
        )
        self.order = Order.objects.create(user=self.user, total_amount=1180.0)
        from order_manager.models import OrderItem, Payment, Product

        p = Product.objects.create(
            sku="S1", name="Widget", weight_kg=0.5, length_cm=10, width_cm=10,
            height_cm=10, price=500.0,
        )
        OrderItem.objects.create(
            order=self.order, product=p, quantity=2, unit_price=500.0,
            total_price=1000.0, sku_code="S1",
        )
        Payment.objects.create(
            order=self.order, amount=1180.0, method="prepaid", tax_percent=18.0,
        )
        # OrderItem.save() runs calculate_total() -> total_amount becomes 1000;
        # the merchant's declared selling price (incl. tax) is 1180, set after.
        self.order.total_amount = 1180.0
        self.order.save(update_fields=["total_amount"])

    def test_summary_reconciles(self):
        s = self.order.invoice_summary()
        self.assertEqual(s["items_subtotal"], 1000.0)
        self.assertEqual(s["tax_amount"], 180.0)          # 18% of 1000, not 1180
        self.assertEqual(s["grand_total"], 1180.0)
        self.assertEqual(s["adjustment"], 0.0)            # 1000 + 180 == 1180
        total = (
            s["items_subtotal"] + s["tax_amount"] + s["shipping_charges"]
            + s["cod_charges"] + s["gift_wrap_charges"] + s["other_charges"]
            - s["discount"] + s["adjustment"]
        )
        self.assertAlmostEqual(total, s["grand_total"], places=2)

    def test_summary_no_payment(self):
        o = Order.objects.create(user=self.user, total_amount=0.0)
        s = o.invoice_summary()
        self.assertEqual(s["items_subtotal"], 0.0)
        self.assertEqual(s["tax_percent"], 0.0)


class RefundShippingIdempotencyTests(TestCase):
    """Order.refund_shipping must credit the wallet once per AWB."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="refund-test@example.com", password="x", role="user"
        )
        self.user.balance = 100.0
        self.user.save(update_fields=["balance"])
        self.order = Order.objects.create(user=self.user, awb_number="AWB-R1")
        # give the order a payment row with a shipping charge
        from order_manager.models import Payment

        self.payment = Payment.objects.create(
            order=self.order, amount=0, shipping_charges=120.0, method="prepaid"
        )

    def _balance(self):
        return User.objects.get(pk=self.user.pk).balance

    def test_single_refund(self):
        t = self.order.refund_shipping()
        self.assertIsNotNone(t)
        self.assertEqual(t.status, "SUCCESS")
        self.assertEqual(self._balance(), 220.0)

    def test_double_click_refunds_once(self):
        t1 = self.order.refund_shipping()
        t2 = self.order.refund_shipping()
        t3 = self.order.refund_shipping()
        self.assertEqual(t1.id, t2.id)
        self.assertEqual(t1.id, t3.id)
        self.assertEqual(self._balance(), 220.0)

    def test_new_awb_refunds_again(self):
        self.order.refund_shipping()
        self.order.awb_number = "AWB-R2"
        self.order.save(update_fields=["awb_number"])
        self.order.refund_shipping()
        self.assertEqual(self._balance(), 340.0)

    def test_refund_defaults_to_the_amount_actually_charged(self):
        """When payment.shipping_charges is stale/0, the refund must still return
        exactly what charge_shipping debited for this AWB (not silently no-op)."""
        self.payment.shipping_charges = 0.0
        self.payment.save(update_fields=["shipping_charges"])
        self.order.charge_shipping(87.50)
        self.assertEqual(self._balance(), 12.50)  # 100 - 87.50

        t = self.order.refund_shipping()
        self.assertIsNotNone(t)
        self.assertEqual(t.status, "SUCCESS")
        self.assertEqual(self._balance(), 100.0)  # fully back

        # idempotent
        self.order.refund_shipping()
        self.assertEqual(self._balance(), 100.0)


class WalletConcurrencySafetyTests(TestCase):
    """User.credit/debit are row-locked read-modify-write on the balance column."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="wallet-test@example.com", password="x", role="user"
        )
        self.user.balance = 100.0
        self.user.save(update_fields=["balance"])

    def test_credit_debit_roundtrip(self):
        self.assertTrue(self.user.credit(50.0))
        self.assertEqual(User.objects.get(pk=self.user.pk).balance, 150.0)
        self.assertTrue(self.user.debit(70.0))
        self.assertEqual(User.objects.get(pk=self.user.pk).balance, 80.0)

    def test_debit_respects_min_balance(self):
        self.assertFalse(self.user.debit(999.0))
        self.assertEqual(User.objects.get(pk=self.user.pk).balance, 100.0)

    def test_debit_only_writes_balance_column(self):
        # a stale in-memory field on `self` must not be written back by debit()
        self.user.commission = 999.0  # never persisted
        self.user.debit(10.0)
        self.assertEqual(User.objects.get(pk=self.user.pk).commission, 0.0)
