from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.accounts.models import User
from apps.billing.models import (
    AppliedDiscount, BillingRun, DiscountRule, Invoice, InvoiceLine, TaxRule,
)
from apps.billing.services import (
    cancel_invoice, confirm_invoice, create_discount_rule, mark_printed,
    preview_billing_day, run_billing_day, send_invoice,
)
from apps.common.timeutils import Frequency
from apps.customers.models import Customer
from apps.payments.models import Payment
from apps.payments.services import record_payment, remove_payment
from apps.products.models import Plan, Product, ProductVariant
from apps.subscriptions import services as sub_services
from apps.subscriptions.models import Subscription


def staff_user(email="billing-rep@x.io"):
    return User.objects.create_user(email, "Sunshine!9qZ", role=User.Role.STAFF)


_ADMIN_SEQ = iter(range(1, 1000))


def admin_user():
    return User.objects.create_user(f"admin-{next(_ADMIN_SEQ)}@x.io", "Sunshine!9qZ",
                                    role=User.Role.ADMIN)


class BillingTestCase(TestCase):
    def setUp(self):
        self.actor = staff_user()
        self.customer = Customer.objects.create(name="Acme Ltd")
        self.product = Product.objects.create(
            name="Cloud Suite", sales_price=Decimal("100.00"), cost_price=Decimal("40.00")
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute="brand", value="Odoo", price_delta=Decimal("560.00")
        )
        self.tax = TaxRule.objects.create(name="GST", rate=Decimal("18.00"))
        self.plan = Plan.objects.create(
            product=self.product, name="Monthly", billing_frequency=Frequency.MONTHLY,
            price=Decimal("100.00"), minimum_quantity=1, availability_start=date(2025, 1, 1),
        )

    def active_sub(self, *, start=date(2026, 1, 1), expiry=None, variant=None, tax=True,
                   quantity=1, plan=None, customer=None):
        plan = plan or self.plan
        sub = sub_services.create_subscription(
            customer=customer or self.customer, plan=plan, start_date=start, expiry_date=expiry,
            actor=self.actor,
        )
        sub_services.add_line(
            sub=sub, product=self.product, variant=variant,
            tax_rule=self.tax if tax else None, quantity=quantity, actor=self.actor,
        )
        sub_services.send_quotation(sub=sub, actor=self.actor)
        sub_services.confirm(sub=sub, actor=self.actor, on=sub.start_date)
        sub_services.activate(sub=sub, actor=self.actor)
        return sub


class BillingRunTests(BillingTestCase):
    def test_run_creates_one_draft_invoice_per_due_period(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 4, 1))
        run = run_billing_day(on=date(2026, 3, 15), actor=self.actor)
        invoices = list(sub.invoices.order_by("period_start"))
        self.assertEqual(len(invoices), 3)
        self.assertEqual([(i.period_start, i.period_end) for i in invoices],
                         [(date(2026, 1, 1), date(2026, 2, 1)),
                          (date(2026, 2, 1), date(2026, 3, 1)),
                          (date(2026, 3, 1), date(2026, 4, 1))])
        self.assertTrue(all(i.status == Invoice.Status.DRAFT for i in invoices))
        self.assertEqual(run.billed_count, 3)
        self.assertEqual(run.skipped_count, 0)

    def test_rerun_is_idempotent_never_double_bills(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 3, 1))
        first = run_billing_day(on=date(2026, 1, 15), actor=self.actor)
        count = sub.invoices.count()
        again = run_billing_day(on=date(2026, 1, 15), actor=self.actor)
        self.assertEqual(sub.invoices.count(), count)
        self.assertEqual(again.billed_count, 0)
        self.assertEqual(again.skipped_count, first.billed_count)

    def test_paused_subscriptions_are_skipped_not_cancelled(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 6, 1))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=True, on=date(2026, 1, 1))
        run = run_billing_day(on=date(2026, 1, 15), actor=self.actor)
        self.assertEqual(run.billed_count, 0)
        # Resume at the next period boundary: the paused period is dropped, not
        # deferred, so the run bills the current period only (never a backlog).
        sub_services.set_paused(sub=sub, actor=self.actor, paused=False, on=date(2026, 2, 1))
        run2 = run_billing_day(on=date(2026, 2, 15), actor=self.actor)
        self.assertEqual(run2.billed_count, 1)
        self.assertEqual(sub.invoices.filter(period_start=date(2026, 1, 1)).count(), 0)
        self.assertEqual(sub.invoices.filter(period_start=date(2026, 2, 1)).count(), 1)

    def test_only_non_cancelled_invoices_block_rebilling(self):
        """ADR 0002: cancelling frees the period for the next run."""
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        invoice = sub.invoices.get()
        cancel_invoice(invoice=invoice, actor=self.actor, reason="typo")
        run = run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        self.assertEqual(run.billed_count, 1)
        self.assertEqual(sub.invoices.filter(status=Invoice.Status.DRAFT).count(), 1)
        self.assertEqual(sub.invoices.filter(status=Invoice.Status.CANCELLED).count(), 1)
        self.assertNotEqual(sub.invoices.get(status=Invoice.Status.DRAFT).number, invoice.number)

    def test_unique_index_is_the_final_arbiter(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(
                    number="INV-DUPE", subscription=sub, customer=self.customer,
                    period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
                    status=Invoice.Status.CONFIRMED,
                )

    def test_invoice_content_snapshots_lines_and_tax(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1),
                              variant=self.variant, quantity=2)
        run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        invoice = sub.invoices.get()
        line = invoice.lines.get()
        self.assertEqual(line.description, "Cloud Suite — Odoo")
        self.assertEqual(line.unit_price, Decimal("660.00"))
        self.assertEqual(line.tax_rate, Decimal("18.00"))
        self.assertEqual(invoice.subtotal, Decimal("1320.00"))
        self.assertEqual(invoice.tax_total, Decimal("237.60"))
        self.assertEqual(invoice.total, Decimal("1557.60"))

    def test_invoice_total_does_not_move_when_product_repriced(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        invoice = sub.invoices.get()
        before = invoice.total
        self.product.sales_price = Decimal("999.00")
        self.product.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice.total, before)

    def test_expired_subscriptions_are_not_billed(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 1, 31))
        during = run_billing_day(on=date(2026, 1, 15), actor=self.actor)
        self.assertEqual(during.billed_count, 1)
        after = run_billing_day(on=date(2026, 2, 5), actor=self.actor)
        self.assertEqual(after.billed_count, 0)
        self.assertEqual(sub.invoices.count(), 1)

    def test_non_staff_cannot_trigger_runs(self):
        portal = User.objects.create_user("portal-run@x.io", "Sunshine!9qZ",
                                         role=User.Role.CUSTOMER, customer=self.customer)
        self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        with self.assertRaises(PermissionDenied):
            run_billing_day(on=date(2026, 1, 5), actor=portal)


class InvoiceLifecycleTests(BillingTestCase):
    def setUp(self):
        super().setUp()
        self.sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        self.invoice = self.sub.invoices.get()

    def test_confirm_sets_issue_date_and_due_date_from_payment_terms(self):
        invoice = confirm_invoice(invoice=self.invoice, actor=self.actor)
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)
        self.assertIsNotNone(invoice.issued_at)
        self.assertEqual(invoice.due_date, invoice.issued_at.date() + timedelta(days=30))

    def test_double_confirm_rejected(self):
        confirm_invoice(invoice=self.invoice, actor=self.actor)
        with self.assertRaises(ValidationError):
            confirm_invoice(invoice=self.invoice, actor=self.actor)

    def test_send_requires_confirmed(self):
        with self.assertRaises(ValidationError):
            send_invoice(invoice=self.invoice, actor=self.actor)

    def test_cancel_confirmed_needs_payments_removed_first(self):
        confirm_invoice(invoice=self.invoice, actor=self.actor)
        record_payment(invoice=self.invoice, actor=self.actor, amount=Decimal("50.00"),
                       method=Payment.Method.BANK_TRANSFER)
        with self.assertRaises(ValidationError):
            cancel_invoice(invoice=self.invoice, actor=self.actor)
        payment = self.invoice.payments.get()
        remove_payment(payment=payment, actor=self.actor)
        cancel_invoice(invoice=self.invoice, actor=self.actor)
        self.assertEqual(self.invoice.status, Invoice.Status.CANCELLED)

    def test_cancelled_is_terminal(self):
        cancel_invoice(invoice=self.invoice, actor=self.actor)
        with self.assertRaises(ValidationError):
            confirm_invoice(invoice=self.invoice, actor=self.actor)
        with self.assertRaises(ValidationError):
            cancel_invoice(invoice=self.invoice, actor=self.actor)

    def test_print_allowed_unless_cancelled(self):
        invoice = mark_printed(invoice=self.invoice, actor=self.actor)
        self.assertIsNotNone(invoice.printed_at)
        cancel_invoice(invoice=self.invoice, actor=self.actor)
        with self.assertRaises(ValidationError):
            mark_printed(invoice=self.invoice, actor=self.actor)


class PaymentTests(BillingTestCase):
    def setUp(self):
        super().setUp()
        self.sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        self.invoice = self.sub.invoices.get()
        confirm_invoice(invoice=self.invoice, actor=self.actor)

    def test_partial_payment_keeps_invoice_confirmed_and_outstanding(self):
        record_payment(invoice=self.invoice, actor=self.actor, amount=Decimal("59.00"),
                       method=Payment.Method.CARD)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("59.00"))
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)
        self.assertTrue(self.invoice.is_outstanding)
        self.assertEqual(self.invoice.amount_due, Decimal("59.00"))

    def test_exact_total_flips_to_paid(self):
        record_payment(invoice=self.invoice, actor=self.actor, amount=self.invoice.total,
                       method=Payment.Method.BANK_TRANSFER)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertFalse(self.invoice.is_outstanding)

    def test_overpayment_refused(self):
        with self.assertRaises(ValidationError):
            record_payment(invoice=self.invoice, actor=self.actor,
                           amount=self.invoice.total + Decimal("0.01"),
                           method=Payment.Method.CASH)

    def test_draft_invoice_cannot_receive_money(self):
        other = self.active_sub(start=date(2026, 3, 1), expiry=date(2026, 4, 1))
        run_billing_day(on=date(2026, 3, 15), actor=self.actor)
        draft = other.invoices.get()
        self.assertEqual(draft.status, Invoice.Status.DRAFT)
        with self.assertRaises(ValidationError):
            record_payment(invoice=draft, actor=self.actor, amount=Decimal("1.00"),
                           method=Payment.Method.CASH)

    def test_payment_on_cancelled_invoice_refused(self):
        cancel_invoice(invoice=self.invoice, actor=self.actor)
        with self.assertRaises(ValidationError):
            record_payment(invoice=self.invoice, actor=self.actor, amount=Decimal("1.00"),
                           method=Payment.Method.CASH)

    def test_removing_payment_reverts_paid_to_confirmed(self):
        p = record_payment(invoice=self.invoice, actor=self.actor, amount=self.invoice.total,
                           method=Payment.Method.CARD)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        remove_payment(payment=p, actor=self.actor)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(self.invoice.amount_paid, Decimal("0.00"))

    def test_non_staff_cannot_record(self):
        portal = User.objects.create_user("portal-pay@x.io", "Sunshine!9qZ",
                                          role=User.Role.CUSTOMER, customer=self.customer)
        with self.assertRaises(PermissionDenied):
            record_payment(invoice=self.invoice, actor=portal, amount=Decimal("5.00"),
                           method=Payment.Method.CARD)

    def test_overdue_flag_tracks_due_date(self):
        self.invoice.due_date = date(2026, 1, 20)
        self.invoice.save(update_fields=["due_date"])
        self.assertFalse(self.invoice.is_overdue(on=date(2026, 1, 10)))
        self.assertTrue(self.invoice.is_overdue(on=date(2026, 2, 1)))


class DiscountTests(BillingTestCase):
    def make_rule(self, *, name, kind=DiscountRule.Kind.PERCENT, value="10.00",
                  scope=DiscountRule.Scope.PRODUCT, admin=None, applies_from=date(2026, 1, 1),
                  **kw):
        return create_discount_rule(
            name=name, kind=kind, value=Decimal(value), scope=scope,
            applies_from=applies_from, actor=admin or admin_user(), **kw
        )

    def bill(self, sub, on=date(2026, 1, 5)):
        run_billing_day(on=on, actor=self.actor)
        return sub.invoices.get()

    def test_percent_product_discount_reduces_line_and_tax(self):
        rule = self.make_rule(name="Loyalty 10")
        rule.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        line = inv.lines.get()
        self.assertEqual(line.base_amount, Decimal("100.00"))
        self.assertEqual(line.discount, Decimal("10.00"))
        self.assertEqual(line.amount, Decimal("90.00"))
        self.assertEqual(line.tax_amount, Decimal("16.20"))  # 18% on the discounted amount
        self.assertEqual(inv.total, Decimal("106.20"))
        applied = inv.applied_discounts.get()
        self.assertEqual(applied.rule, rule)
        self.assertEqual(applied.line, line)

    def test_best_rule_wins_and_never_stacks_on_one_line(self):
        r1 = self.make_rule(name="Ten", value="10.00")
        r1.products.add(self.product)
        r2 = self.make_rule(name="Twenty", value="20.00")
        r2.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        line = inv.lines.get()
        self.assertEqual(line.discount, Decimal("20.00"))
        self.assertEqual(line.applied_discounts.count(), 1)

    def test_fixed_amount_capped_at_line_base(self):
        rule = self.make_rule(name="Huge", kind=DiscountRule.Kind.AMOUNT, value="500.00")
        rule.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        self.assertEqual(inv.lines.get().discount, Decimal("100.00"))
        self.assertEqual(inv.total, Decimal("0.00"))

    def test_minimum_quantity_gates_application(self):
        rule = self.make_rule(name="Seats5", minimum_quantity=5)
        rule.products.add(self.product)
        small = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1), quantity=4)
        self.bill(small)
        self.assertEqual(small.invoices.get().discount_total, Decimal("0.00"))
        big = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1), quantity=5)
        self.bill(big)
        big.refresh_from_db()
        self.assertEqual(big.invoices.get().discount_total, Decimal("50.00"))  # 10% of 5x100

    def test_minimum_amount_gates_product_scope(self):
        rule = self.make_rule(name="Min150", minimum_amount=Decimal("150.00"))
        rule.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1), quantity=1)
        inv = self.bill(sub)
        self.assertEqual(inv.discount_total, Decimal("0.00"))

    def test_window_bounds_stop_application(self):
        expired = self.make_rule(name="Expired", applies_from=date(2025, 1, 1),
                                 applies_until=date(2025, 12, 31))
        expired.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        self.assertEqual(inv.discount_total, Decimal("0.00"))

        future = self.make_rule(name="Future", applies_from=date(2027, 1, 1))
        future.products.add(self.product)
        sub2 = self.active_sub(start=date(2026, 2, 1), expiry=date(2026, 4, 1))
        run_billing_day(on=date(2026, 3, 5), actor=self.actor)  # bills Feb AND Mar periods
        sub2.refresh_from_db()
        self.assertEqual(sub2.invoices.count(), 2)
        for inv in sub2.invoices.all():
            self.assertEqual(inv.discount_total, Decimal("0.00"))

    def test_usage_limit_stops_after_n_invoices(self):
        rule = self.make_rule(name="Once", usage_limit=1)
        rule.products.add(self.product)
        s1 = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv1 = self.bill(s1)
        self.assertEqual(inv1.discount_total, Decimal("10.00"))

        c2 = Customer.objects.create(name="Second Co")
        s2 = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1), customer=c2)
        self.bill(s2)
        s2.refresh_from_db()
        self.assertEqual(s2.invoices.get().discount_total, Decimal("0.00"))  # exhausted
        self.assertEqual(rule.usage(), 1)

    def test_cancelled_invoice_returns_the_use(self):
        rule = self.make_rule(name="Once2", usage_limit=1)
        rule.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        self.assertEqual(rule.usage(), 1)
        cancel_invoice(invoice=inv, actor=self.actor)
        self.assertEqual(rule.usage(), 0)
        run_billing_day(on=date(2026, 1, 5), actor=self.actor)  # rebills the freed period
        sub.refresh_from_db()
        fresh = sub.invoices.get(status=Invoice.Status.DRAFT)
        self.assertEqual(fresh.discount_total, Decimal("10.00"))

    def test_subscription_scope_applies_after_line_discounts(self):
        prod_rule = self.make_rule(name="Line20", value="20.00")
        prod_rule.products.add(self.product)
        order_rule = self.make_rule(name="Order10", scope=DiscountRule.Scope.SUBSCRIPTION,
                                    value="10.00")
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        # 100 base - 20 line = 80; order -10% of 80 = -8 => 72 + 18% tax = 84.96
        self.assertEqual(inv.subtotal, Decimal("100.00"))
        self.assertEqual(inv.discount_total, Decimal("28.00"))
        self.assertEqual(inv.tax_total, Decimal("12.96"))
        self.assertEqual(inv.total, Decimal("84.96"))
        self.assertEqual(inv.applied_discounts.filter(line__isnull=True).get().rule, order_rule)

    def test_order_discount_allocated_exactly_across_lines(self):
        """Odd-cent pro-rata split must sum to the discount total with no drift."""
        other = Product.objects.create(name="Addon", sales_price=Decimal("33.33"),
                                       cost_price=Decimal("1.00"))
        sub = sub_services.create_subscription(
            customer=self.customer, plan=self.plan, start_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), actor=self.actor,
        )
        sub_services.add_line(sub=sub, product=self.product, tax_rule=self.tax, actor=self.actor)
        sub_services.add_line(sub=sub, product=other, tax_rule=self.tax, actor=self.actor)
        sub_services.send_quotation(sub=sub, actor=self.actor)
        sub_services.confirm(sub=sub, actor=self.actor, on=date(2026, 1, 1))
        sub_services.activate(sub=sub, actor=self.actor)
        rule = self.make_rule(name="Third", scope=DiscountRule.Scope.SUBSCRIPTION,
                              value="33.33")
        inv = self.bill(sub)
        parts = [l.discount for l in inv.lines.all()]
        expected = (inv.subtotal * rule.value / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(inv.discount_total, expected)
        self.assertEqual(sum(parts, Decimal("0.00")), inv.discount_total)
        # base = 100 + 33.33 = 133.33 -> 33.33% = 44.44 (odd cents split across 2 lines)
        self.assertEqual(inv.subtotal, Decimal("133.33"))
        self.assertEqual(inv.discount_total, Decimal("44.44"))
        self.assertCountEqual([str(p) for p in parts], ["33.33", "11.11"])

    def test_rule_inactive_stops_applying(self):
        rule = self.make_rule(name="Sleepy")
        rule.active = False
        rule.save()
        rule.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        self.assertEqual(inv.discount_total, Decimal("0.00"))

    def test_empty_product_list_means_any_product(self):
        self.make_rule(name="Universal")  # no products linked
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        self.assertEqual(inv.discount_total, Decimal("10.00"))

    def test_deactivate_keeps_history_valid(self):
        rule = self.make_rule(name="SoonDone")
        rule.products.add(self.product)
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        inv = self.bill(sub)
        self.assertEqual(inv.discount_total, Decimal("10.00"))
        from apps.billing.services import deactivate_discount_rule
        deactivate_discount_rule(rule=rule, actor=admin_user())
        # an already-applied discount on an issued invoice is untouched
        self.assertEqual(inv.applied_discounts.count(), 1)


class DiscountConcurrencyTests(TransactionTestCase):
    """The last usage slot must not be consumed twice by parallel runs."""

    def setUp(self):
        self.actor = staff_user("race-rep@x.io")
        self.customer = Customer.objects.create(name="Race Co")
        self.product = Product.objects.create(name="RaceProd", sales_price=Decimal("100.00"),
                                              cost_price=Decimal("10.00"))
        self.plan = Plan.objects.create(
            product=self.product, name="RacePlan", billing_frequency=Frequency.MONTHLY,
            price=Decimal("100.00"), minimum_quantity=1, availability_start=date(2025, 1, 1),
        )
        self.rule = DiscountRule.objects.create(
            name="FinalSlot", kind=DiscountRule.Kind.PERCENT, value=Decimal("50.00"),
            scope=DiscountRule.Scope.PRODUCT, usage_limit=1, applies_from=date(2026, 1, 1),
        )
        self.rule.products.add(self.product)
        for _ in range(2):
            sub = sub_services.create_subscription(
                customer=self.customer, plan=self.plan, start_date=date(2026, 1, 1),
                expiry_date=date(2026, 2, 1), actor=self.actor,
            )
            sub_services.add_line(sub=sub, product=self.product, actor=self.actor)
            sub_services.send_quotation(sub=sub, actor=self.actor)
            sub_services.confirm(sub=sub, actor=self.actor, on=date(2026, 1, 1))
            sub_services.activate(sub=sub, actor=self.actor)

    def test_parallel_runs_consume_one_use(self):
        import threading

        done = threading.Barrier(2)
        errors = []

        def run_it():
            try:
                done.wait()
                run_billing_day(on=date(2026, 1, 5), actor=self.actor)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        ts = [threading.Thread(target=run_it) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [], f"runs crashed: {errors}")
        self.assertEqual(AppliedDiscount.objects.count(), 1)
        self.assertEqual(self.rule.usage(), 1)
        self.assertEqual(Invoice.objects.filter(discount_total__gt=0).count(), 1)


class DiscountAdminOnlyTests(BillingTestCase):
    def test_only_admin_may_create_rules(self):
        with self.assertRaises(PermissionDenied):
            create_discount_rule(
                name="Nope", kind=DiscountRule.Kind.PERCENT, value=Decimal("10.00"),
                scope=DiscountRule.Scope.PRODUCT, applies_from=date(2026, 1, 1),
                actor=self.actor,  # staff, not admin
            )
        rule = create_discount_rule(
            name="Okay", kind=DiscountRule.Kind.PERCENT, value=Decimal("10.00"),
            scope=DiscountRule.Scope.PRODUCT, applies_from=date(2026, 1, 1), actor=admin_user(),
        )
        self.assertEqual(rule.created_by.role, User.Role.ADMIN)

    def test_percent_over_100_refused(self):
        with self.assertRaises(ValidationError):
            create_discount_rule(
                name="Robbery", kind=DiscountRule.Kind.PERCENT, value=Decimal("100.01"),
                scope=DiscountRule.Scope.PRODUCT, applies_from=date(2026, 1, 1),
                actor=admin_user(),
            )

    def test_inverted_window_refused(self):
        with self.assertRaises(ValidationError):
            create_discount_rule(
                name="Backwards", kind=DiscountRule.Kind.PERCENT, value=Decimal("10.00"),
                scope=DiscountRule.Scope.PRODUCT, applies_from=date(2026, 5, 1),
                applies_until=date(2026, 4, 1), actor=admin_user(),
            )

    def test_scope_mix_refused(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        admin = admin_user()
        rule = create_discount_rule(
            name="Mixed", kind=DiscountRule.Kind.PERCENT, value=Decimal("10.00"),
            scope=DiscountRule.Scope.PRODUCT, applies_from=date(2026, 1, 1), actor=admin,
        )
        with self.assertRaises(ValidationError):
            create_discount_rule(
                name="Mixed2", kind=DiscountRule.Kind.PERCENT, value=Decimal("10.00"),
                scope=DiscountRule.Scope.PRODUCT, applies_from=date(2026, 1, 1),
                subscription_ids=[sub.id], actor=admin,
            )


# ---------------------------------------------------------------------------
# Regression: the seams the green suite could not see (time boundaries,
# batch isolation, pause semantics). Each test below failed before the fix.
# ---------------------------------------------------------------------------

class BillingCompletenessTests(BillingTestCase):
    def test_unbilled_periods_of_an_ended_term_are_still_billed(self):
        """
        The team misses billing day and the term then ends. Every period that
        fell due inside the term must still be invoiced — silence here is
        revenue the company never recovers.
        """
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 4, 1))
        run = run_billing_day(on=date(2026, 5, 1), actor=self.actor)
        self.assertEqual(run.billed_count, 3)
        self.assertEqual(
            [(i.period_start, i.period_end) for i in sub.invoices.order_by("period_start")],
            [(date(2026, 1, 1), date(2026, 2, 1)),
             (date(2026, 2, 1), date(2026, 3, 1)),
             (date(2026, 3, 1), date(2026, 4, 1))],
        )

    def test_periods_never_run_past_the_term(self):
        """Scanning an ended term must not invent a period beyond expiry."""
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 3, 15))
        run_billing_day(on=date(2026, 6, 1), actor=self.actor)
        self.assertEqual(
            [i.period_start for i in sub.invoices.order_by("period_start")],
            [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
        )

    def test_preview_reports_missed_periods_of_an_ended_term(self):
        self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 4, 1))
        preview = preview_billing_day(on=date(2026, 5, 1))
        self.assertEqual(preview["invoices"], 3)
        self.assertEqual(preview["missed_periods"], 3)
        self.assertTrue(preview["items"][0]["term_ended"])
        self.assertEqual(Invoice.objects.count(), 0)

    def test_preview_does_not_flag_a_running_term_as_missed(self):
        self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 6, 1))
        preview = preview_billing_day(on=date(2026, 2, 15))
        self.assertEqual(preview["invoices"], 2)
        self.assertEqual(preview["missed_periods"], 0)
        self.assertFalse(any(item["term_ended"] for item in preview["items"]))

    def test_a_broken_record_does_not_abort_the_batch(self):
        healthy_a = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))
        broken = self._subscription_on_broken_frequency()
        healthy_b = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 2, 1))

        run = run_billing_day(on=date(2026, 1, 5), actor=self.actor)

        self.assertEqual(run.billed_count, 2)
        self.assertEqual(run.failed_count, 1)
        self.assertTrue(healthy_a.invoices.exists())
        self.assertTrue(healthy_b.invoices.exists())
        self.assertFalse(broken.invoices.exists())
        failure = run.report["failed"][0]
        self.assertEqual(failure["subscription"], broken.number)
        self.assertIn("unknown billing frequency", failure["error"])

    def test_the_billing_run_row_survives_a_failed_record(self):
        self._subscription_on_broken_frequency()
        run = run_billing_day(on=date(2026, 1, 5), actor=self.actor)
        self.assertTrue(BillingRun.objects.filter(pk=run.pk).exists())
        self.assertIsNotNone(BillingRun.objects.get(pk=run.pk).finished_at)

    def _subscription_on_broken_frequency(self):
        """A plan whose frequency no period arithmetic understands (bad import)."""
        plan = Plan.objects.create(
            product=self.product, name="Hourly", billing_frequency="hourly",
            price=Decimal("10.00"), minimum_quantity=1,
            availability_start=date(2025, 1, 1),
        )
        sub = sub_services.create_subscription(
            customer=self.customer, plan=plan, start_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), actor=self.actor,
        )
        sub_services.add_line(sub=sub, product=self.product, quantity=1, actor=self.actor)
        sub_services.send_quotation(sub=sub, actor=self.actor)
        sub_services.confirm(sub=sub, actor=self.actor, on=sub.start_date)
        sub_services.activate(sub=sub, actor=self.actor)
        return sub


class PauseSemanticsTests(BillingTestCase):
    def test_paused_months_are_not_billed_after_resume(self):
        """Pause stops billing; it must not defer three months into one day."""
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 7, 1))
        run_billing_day(on=date(2026, 1, 15), actor=self.actor)
        sub_services.set_paused(sub=sub, actor=self.actor, paused=True, on=date(2026, 2, 1))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=False, on=date(2026, 5, 1))

        run = run_billing_day(on=date(2026, 6, 15), actor=self.actor)

        self.assertEqual(run.billed_count, 2)
        self.assertEqual(
            [i.period_start for i in sub.invoices.order_by("period_start")],
            [date(2026, 1, 1), date(2026, 5, 1), date(2026, 6, 1)],
        )
        self.assertEqual(
            sub.invoices.filter(period_start__in=[
                date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1),
            ]).count(),
            0,
        )

    def test_a_partially_paused_period_is_not_billed(self):
        """Any period overlapping a pause is dropped, never pro-rated."""
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 6, 1))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=True, on=date(2026, 2, 10))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=False, on=date(2026, 3, 20))

        run_billing_day(on=date(2026, 4, 15), actor=self.actor)

        self.assertEqual(
            [i.period_start for i in sub.invoices.order_by("period_start")],
            [date(2026, 1, 1), date(2026, 4, 1)],
        )

    def test_a_same_day_pause_loses_nothing(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 3, 1))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=True, on=date(2026, 1, 10))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=False, on=date(2026, 1, 10))
        run = run_billing_day(on=date(2026, 1, 15), actor=self.actor)
        self.assertEqual(run.billed_count, 1)

    def test_pause_spans_are_recorded(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 4, 1))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=True, on=date(2026, 2, 1))
        open_span = sub.pause_periods.get()
        self.assertEqual(open_span.started_on, date(2026, 2, 1))
        self.assertIsNone(open_span.ended_on)

        sub_services.set_paused(sub=sub, actor=self.actor, paused=False, on=date(2026, 3, 1))
        open_span.refresh_from_db()
        self.assertEqual(open_span.ended_on, date(2026, 3, 1))

    def test_preview_skips_paused_periods(self):
        sub = self.active_sub(start=date(2026, 1, 1), expiry=date(2026, 5, 1))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=True, on=date(2026, 2, 1))
        sub_services.set_paused(sub=sub, actor=self.actor, paused=False, on=date(2026, 4, 1))
        preview = preview_billing_day(on=date(2026, 4, 15))
        self.assertEqual(
            [item["period_start"] for item in preview["items"]],
            ["2026-01-01", "2026-04-01"],
        )
