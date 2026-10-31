from datetime import date, timedelta
from decimal import Decimal

from apps.api.tests.helpers import ApiTestCase
from apps.billing.models import Invoice
from apps.payments.models import Payment


class BillingTestCase(ApiTestCase):
    """One active monthly subscription starting 2026-11-01, ready to bill."""

    def setUp(self):
        super().setUp()
        self.auth(self.staff)
        self.product = self.make_product()
        self.tax = self.make_tax()
        self.plan = self.make_plan(product=self.product)
        created = self.client.post("/api/subscriptions/", {
            "customer": self.customer.id,
            "plan": self.plan.id,
            "start_date": "2026-11-01",
            "expiry_date": "2027-02-01",
            "lines": [{"product": self.product.id, "quantity": 1, "tax_rule": self.tax.id}],
        }, format="json").json()
        self.subscription = created
        base = f"/api/subscriptions/{created['id']}"
        self.client.post(f"{base}/send-quotation/")
        self.client.post(f"{base}/confirm/")
        self.client.post(f"{base}/activate/")

    def run_billing(self, on="2026-11-15", dry_run=False):
        return self.client.post(
            "/api/billing-runs/run/", {"on": on, "dry_run": dry_run}, format="json"
        )

    def invoice(self):
        return Invoice.objects.get(subscription_id=self.subscription["id"])


class BillingRunApiTests(BillingTestCase):
    def test_dry_run_reports_without_writing(self):
        response = self.run_billing(dry_run=True)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["invoices"], 1)
        self.assertEqual(body["items"][0]["subscription"], self.subscription["number"])
        self.assertEqual(Invoice.objects.count(), 0)

    def test_run_creates_exactly_one_invoice_per_period(self):
        response = self.run_billing()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["billed_count"], 1)
        self.assertEqual(Invoice.objects.count(), 1)

        again = self.run_billing()
        self.assertEqual(again.json()["billed_count"], 0)
        self.assertEqual(again.json()["skipped_count"], 1)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_invoice_snapshots_lines_and_tax(self):
        self.run_billing()
        invoice = self.invoice()
        self.assertEqual(invoice.subtotal, Decimal("100.00"))
        self.assertEqual(invoice.tax_total, Decimal("18.00"))
        self.assertEqual(invoice.total, Decimal("118.00"))
        self.assertEqual(invoice.lines.count(), 1)
        self.assertEqual(invoice.lines.first().tax_rate, Decimal("18.000"))

    def test_billing_run_history_is_listable(self):
        self.run_billing()
        response = self.client.get("/api/billing-runs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["billed_count"], 1)

    def test_bad_date_is_400(self):
        response = self.client.post("/api/billing-runs/run/", {"on": "tomorrow"},
                                    format="json")
        self.assertEqual(response.status_code, 400)


class InvoiceApiTests(BillingTestCase):
    def setUp(self):
        super().setUp()
        self.run_billing()
        self.invoice = self.invoice()
        self.url = f"/api/invoices/{self.invoice.id}"

    def test_confirm_sets_issue_date_and_due_date(self):
        response = self.client.post(f"{self.url}/confirm/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "confirmed")
        expected_due = date.today() + timedelta(days=30)
        self.assertEqual(body["due_date"], expected_due.isoformat())

    def test_confirming_twice_is_400(self):
        self.client.post(f"{self.url}/confirm/")
        response = self.client.post(f"{self.url}/confirm/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json()["errors"])

    def test_draft_invoice_cannot_be_sent(self):
        response = self.client.post(f"{self.url}/send/")
        self.assertEqual(response.status_code, 400)

    def test_confirmed_invoice_can_be_sent_and_printed(self):
        self.client.post(f"{self.url}/confirm/")
        self.assertEqual(self.client.post(f"{self.url}/send/").status_code, 200)
        printed = self.client.post(f"{self.url}/mark-printed/")
        self.assertEqual(printed.status_code, 200)
        self.assertIsNotNone(printed.json()["printed_at"])

    def test_detail_includes_lines_and_totals(self):
        response = self.client.get(f"{self.url}/")
        body = response.json()
        self.assertEqual(body["total"], "118.00")
        self.assertEqual(body["amount_due"], "118.00")
        self.assertEqual(body["status"], "draft")
        self.assertEqual(len(body["lines"]), 1)

    def test_list_shape_is_light_and_filterable(self):
        response = self.client.get("/api/invoices/", {"status": "draft"})
        self.assertEqual(response.json()["count"], 1)
        self.assertNotIn("lines", response.json()["results"][0])

    def test_overdue_filter(self):
        self.client.post(f"{self.url}/confirm/")
        Invoice.objects.filter(pk=self.invoice.pk).update(
            due_date=date.today() - timedelta(days=5)
        )
        response = self.client.get("/api/invoices/", {"overdue": "true"})
        self.assertEqual(response.json()["count"], 1)
        detail = self.client.get(f"{self.url}/").json()
        self.assertTrue(detail["is_overdue"])

    def test_portal_sees_only_its_own_invoices(self):
        self.auth(self.customer_user)
        response = self.client.get("/api/invoices/")
        self.assertEqual(response.json()["count"], 1)
        self.auth(self.other_portal)
        self.assertEqual(self.client.get("/api/invoices/").json()["count"], 0)


class PaymentApiTests(BillingTestCase):
    def setUp(self):
        super().setUp()
        self.run_billing()
        self.invoice = self.invoice()
        self.url = f"/api/invoices/{self.invoice.id}"
        self.client.post(f"{self.url}/confirm/")

    def pay(self, amount="118.00", invoice=None):
        return self.client.post("/api/payments/", {
            "invoice": (invoice or self.invoice).id,
            "amount": amount,
            "method": "card",
            "reference": "TXN-1",
        }, format="json")

    def test_full_payment_marks_the_invoice_paid(self):
        response = self.pay()
        self.assertEqual(response.status_code, 201)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(self.invoice.amount_paid, Decimal("118.00"))
        self.assertEqual(self.client.get(f"{self.url}/").json()["amount_due"],
                         "0.00")

    def test_partial_payments_accumulate(self):
        self.pay("18.00")
        self.pay("100.00")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("118.00"))
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_overpayment_is_refused(self):
        response = self.pay("118.01")
        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.json()["errors"])
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_against_a_draft_is_refused(self):
        draft_invoice = Invoice.objects.create(
            number="INV-2026-999999", subscription=self.invoice.subscription,
            customer=self.customer, period_start=date(2026, 12, 1),
            period_end=date(2027, 1, 1), total=Decimal("10.00"),
        )
        response = self.pay("10.00", invoice=draft_invoice)
        self.assertEqual(response.status_code, 400)
        self.assertIn("invoice", response.json()["errors"])

    def test_removing_a_payment_drops_the_invoice_back_to_confirmed(self):
        payment = self.pay().json()
        response = self.client.delete(f"/api/payments/{payment['id']}/")
        self.assertEqual(response.status_code, 204)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(self.invoice.amount_paid, Decimal("0.00"))

    def test_ledger_lists_and_filters(self):
        self.pay()
        response = self.client.get("/api/payments/", {"invoice": self.invoice.id})
        self.assertEqual(response.json()["count"], 1)
        response = self.client.get("/api/payments/", {"customer": self.other_customer.id})
        self.assertEqual(response.json()["count"], 0)


class CancellationTests(BillingTestCase):
    def setUp(self):
        super().setUp()
        self.run_billing()
        self.invoice = self.invoice()
        self.url = f"/api/invoices/{self.invoice.id}"
        self.client.post(f"{self.url}/confirm/")

    def test_cancelling_with_payments_attached_is_refused(self):
        payment = self.client.post("/api/payments/", {
            "invoice": self.invoice.id, "amount": "20.00", "method": "cash",
        }, format="json").json()
        response = self.client.post(f"{self.url}/cancel/", {"reason": "mistake"},
                                    format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("payments", response.json()["errors"])
        self.assertTrue(Payment.objects.filter(pk=payment["id"]).exists())

    def test_credit_then_rebill_frees_the_period(self):
        payment = self.client.post("/api/payments/", {
            "invoice": self.invoice.id, "amount": "20.00", "method": "cash",
        }, format="json").json()
        self.client.delete(f"/api/payments/{payment['id']}/")
        response = self.client.post(f"{self.url}/cancel/", {"reason": "wrong customer"},
                                    format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

        rerun = self.run_billing()
        self.assertEqual(rerun.json()["billed_count"], 1)
        fresh = Invoice.objects.filter(
            subscription_id=self.subscription["id"]
        ).exclude(pk=self.invoice.pk).get()
        self.assertNotEqual(fresh.number, self.invoice.number)
        self.assertEqual(fresh.period_start, self.invoice.period_start)

    def test_cancelled_invoice_is_frozen(self):
        self.client.post(f"{self.url}/cancel/", {}, format="json")
        response = self.client.post(f"{self.url}/mark-printed/")
        self.assertEqual(response.status_code, 400)


class DiscountRuleApiTests(BillingTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.admin)

    def rule_payload(self, **overrides):
        payload = {
            "name": "Launch 10",
            "scope": "product",
            "kind": "percent",
            "value": "10.00",
            "applies_from": "2026-01-01",
            "product_ids": [self.product.id],
        }
        payload.update(overrides)
        return payload

    def test_product_discount_reduces_the_line_and_the_tax(self):
        created = self.client.post("/api/discount-rules/", self.rule_payload(),
                                   format="json")
        self.assertEqual(created.status_code, 201)
        self.run_billing()
        invoice = self.invoice()
        self.assertEqual(invoice.discount_total, Decimal("10.00"))
        self.assertEqual(invoice.subtotal, Decimal("100.00"))
        self.assertEqual(invoice.tax_total, Decimal("16.20"))  # 18% of 90
        self.assertEqual(invoice.total, Decimal("106.20"))
        self.assertEqual(invoice.applied_discounts.count(), 1)

    def test_usage_is_counted_per_invoice(self):
        rule_id = self.client.post("/api/discount-rules/", self.rule_payload(),
                                   format="json").json()["id"]
        self.run_billing()
        detail = self.client.get(f"/api/discount-rules/{rule_id}/").json()
        self.assertEqual(detail["usage_count"], 1)
        self.assertEqual(self.client.get("/api/discount-rules/").json()["count"], 1)

    def test_deactivated_rule_stops_applying(self):
        rule_id = self.client.post("/api/discount-rules/", self.rule_payload(
            usage_limit=1
        ), format="json").json()["id"]
        self.run_billing()
        deactivated = self.client.post(f"/api/discount-rules/{rule_id}/deactivate/")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["active"])

        # next month's invoice must be full price
        self.run_billing(on="2026-12-15")
        newest = Invoice.objects.order_by("-period_start").first()
        self.assertEqual(newest.discount_total, Decimal("0.00"))
        self.assertEqual(newest.total, Decimal("118.00"))

    def test_cancelling_the_invoice_returns_the_use(self):
        rule_id = self.client.post("/api/discount-rules/", self.rule_payload(
            usage_limit=1
        ), format="json").json()["id"]
        self.run_billing()
        self.assertEqual(
            self.client.get(f"/api/discount-rules/{rule_id}/").json()["usage_count"], 1
        )
        invoice = self.invoice()
        self.client.post(f"/api/invoices/{invoice.id}/cancel/", {}, format="json")
        self.assertEqual(
            self.client.get(f"/api/discount-rules/{rule_id}/").json()["usage_count"], 0
        )
        rerun = self.run_billing()
        self.assertEqual(rerun.json()["billed_count"], 1)

    def test_percentage_above_one_hundred_is_refused(self):
        response = self.client.post(
            "/api/discount-rules/", self.rule_payload(value="101.00"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("value", response.json()["errors"])

    def test_scope_and_targets_must_agree(self):
        response = self.client.post("/api/discount-rules/", self.rule_payload(
            scope="subscription"
        ), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("product_ids", response.json()["errors"])

    def test_subscription_scoped_rule_applies_once_at_order_level(self):
        response = self.client.post("/api/discount-rules/", {
            "name": "Order 5%", "scope": "subscription", "kind": "percent",
            "value": "5.00", "applies_from": "2026-01-01",
            "subscription_ids": [self.subscription["id"]],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.run_billing()
        invoice = self.invoice()
        self.assertEqual(invoice.discount_total, Decimal("5.00"))
        order_discount = invoice.applied_discounts.get(line__isnull=True)
        self.assertEqual(order_discount.amount, Decimal("5.00"))
