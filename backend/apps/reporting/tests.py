import time
from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import Invoice, TaxRule
from apps.common.timeutils import Frequency
from apps.customers.models import Customer
from apps.payments.models import Payment
from apps.products.models import Plan, Product
from apps.reporting import services
from apps.subscriptions.models import Subscription


def staff(email="rep@x.io"):
    return User.objects.create_user(email, "Sunshine!9qZ", role=User.Role.STAFF)


def portal(email="cust@x.io", customer=None):
    return User.objects.create_user(email, "Sunshine!9qZ", role=User.Role.CUSTOMER,
                                    customer=customer)


class ReportingTestCase(TestCase):
    def setUp(self):
        self.actor = staff()
        self.customer = Customer.objects.create(name="Ledger Co")
        self.product = Product.objects.create(name="Suite", sales_price=Decimal("100.00"),
                                              cost_price=Decimal("10.00"))
        self.tax = TaxRule.objects.create(name="GST", rate=Decimal("18.00"))

    def plan(self, name, frequency):
        return Plan.objects.create(
            product=self.product, name=name, billing_frequency=frequency,
            price=Decimal("100.00"), minimum_quantity=1, availability_start=date(2025, 1, 1),
        )

    def sub(self, *, number, plan, subtotal, stage=Subscription.Stage.ACTIVE, paused=False,
            customer=None):
        return Subscription.objects.create(
            number=number, customer=customer or self.customer, plan=plan, stage=stage,
            start_date=date(2026, 1, 1), expiry_date=date(2027, 1, 1),
            is_paused=paused, subtotal=Decimal(subtotal),
            tax_total=Decimal(subtotal) * Decimal("0.18"),
            total=Decimal(subtotal) * Decimal("1.18"),
        )

    def invoice(self, *, number, sub, total, status=Invoice.Status.CONFIRMED,
                due=date(2026, 2, 15), period_start=date(2026, 1, 1), amount_paid=None,
                issued=date(2026, 1, 5), customer=None):
        from datetime import datetime
        from django.utils import timezone as tz
        from apps.common.timeutils import add_months
        inv = Invoice.objects.create(
            number=number, subscription=sub, customer=customer or sub.customer,
            period_start=period_start, period_end=add_months(period_start, 1), status=status,
            subtotal=Decimal(total), tax_total=Decimal("0.00"), total=Decimal(total),
            amount_paid=Decimal(amount_paid or "0.00"),
            issued_at=tz.make_aware(datetime(issued.year, issued.month, issued.day, 12, 0, 0)),
            due_date=due,
        )
        return inv

    def pay(self, *, invoice, amount, on):
        from apps.payments.services import record_payment
        return record_payment(invoice=invoice, actor=self.actor, amount=Decimal(amount),
                              method=Payment.Method.CARD, paid_on=on)


class MonthWindowTests(ReportingTestCase):
    def test_month_end_defaults_within_year(self):
        self.assertEqual(services.month_end_defaults(date(2026, 3, 17)),
                         (date(2026, 3, 1), date(2026, 3, 31)))

    def test_month_end_defaults_december_boundary(self):
        self.assertEqual(services.month_end_defaults(date(2026, 12, 31)),
                         (date(2026, 12, 1), date(2026, 12, 31)))

    def test_month_end_defaults_leap_february(self):
        self.assertEqual(services.month_end_defaults(date(2024, 2, 10)),
                         (date(2024, 2, 1), date(2024, 2, 29)))

    def test_window_start_only_derives_end(self):
        out = services.summary(start=date(2026, 5, 3), on=date(2026, 9, 9))
        self.assertEqual(out["window"]["start"], "2026-05-03")
        self.assertEqual(out["window"]["end"], "2026-05-31")


class MRRTests(ReportingTestCase):
    def test_frequencies_normalise_to_a_month(self):
        monthly, weekly, daily, yearly = (
            self.plan("m", Frequency.MONTHLY), self.plan("w", Frequency.WEEKLY),
            self.plan("d", Frequency.DAILY), self.plan("y", Frequency.YEARLY),
        )
        self.sub(number="S1", plan=monthly, subtotal="100.00")
        self.sub(number="S2", plan=weekly, subtotal="100.00")   # 100 * 52/12 = 433.33
        self.sub(number="S3", plan=daily, subtotal="100.00")    # 100 * 365/12 = 3041.67
        self.sub(number="S4", plan=yearly, subtotal="1200.00")  # /12 = 100.00
        out = services.summary()
        expected = (Decimal("100.00") + Decimal("433.3333") + Decimal("3041.6667")
                    + Decimal("100.00")).quantize(Decimal("0.01"))
        self.assertEqual(Decimal(out["mrr"]), expected)
        self.assertEqual(out["active_subscriptions"], 4)
        self.assertEqual(Decimal(out["arr"]), (expected * 12).quantize(Decimal("0.01")))

    def test_paused_and_non_active_excluded(self):
        p = self.plan("m", Frequency.MONTHLY)
        self.sub(number="S1", plan=p, subtotal="100.00")
        self.sub(number="S2", plan=p, subtotal="100.00", paused=True)
        self.sub(number="S3", plan=p, subtotal="100.00", stage=Subscription.Stage.CLOSED)
        out = services.summary()
        self.assertEqual(out["active_subscriptions"], 1)
        self.assertEqual(out["paused_subscriptions"], 1)
        self.assertEqual(Decimal(out["mrr"]), Decimal("100.00"))

    def test_customer_filter_scopes_every_metric(self):
        other = Customer.objects.create(name="Other Co")
        p = self.plan("m", Frequency.MONTHLY)
        self.sub(number="S1", plan=p, subtotal="100.00")
        self.sub(number="S2", plan=p, subtotal="50.00", customer=other)
        out = services.summary(customer_id=other.id)
        self.assertEqual(out["active_subscriptions"], 1)
        self.assertEqual(Decimal(out["mrr"]), Decimal("50.00"))


class RevenueTests(ReportingTestCase):
    def setUp(self):
        super().setUp()
        self.p = self.plan("m", Frequency.MONTHLY)
        self.s = self.sub(number="S1", plan=self.p, subtotal="100.00")

    def test_invoiced_excludes_cancelled_invoices(self):
        self.invoice(number="INV-1", sub=self.s, total="100.00")
        self.invoice(number="INV-2", sub=self.s, total="70.00", period_start=date(2026, 2, 1),
                     status=Invoice.Status.CANCELLED)
        out = services.summary(start=date(2026, 1, 1), end=date(2026, 1, 31))
        self.assertEqual(Decimal(out["invoiced_total"]), Decimal("100.00"))

    def test_collected_sums_payments_in_window(self):
        inv = self.invoice(number="INV-1", sub=self.s, total="100.00")
        self.pay(invoice=inv, amount="40.00", on=date(2026, 1, 10))
        self.pay(invoice=inv, amount="60.00", on=date(2026, 1, 20))
        # a second invoice paid next month must not leak into January's window
        feb_inv = self.invoice(number="INV-2", sub=self.s, total="11.00",
                               period_start=date(2026, 2, 1))
        self.pay(invoice=feb_inv, amount="11.00", on=date(2026, 2, 2))
        out = services.summary(start=date(2026, 1, 1), end=date(2026, 1, 31))
        self.assertEqual(Decimal(out["collected_total"]), Decimal("100.00"))

    def test_outstanding_and_overdue_split_on_due_date(self):
        overdue = self.invoice(number="INV-O", sub=self.s, total="100.00",
                               due=date(2026, 1, 31))
        self.pay(invoice=overdue, amount="25.00", on=date(2026, 1, 15))
        fine = self.invoice(number="INV-F", sub=self.s, total="80.00",
                            period_start=date(2026, 2, 1), due=date(2026, 3, 31))
        out = services.summary(start=date(2026, 1, 1), end=date(2026, 3, 31),
                               on=date(2026, 2, 1))
        self.assertEqual(out["overdue"]["count"], 1)
        self.assertEqual(Decimal(out["overdue"]["amount"]), Decimal("75.00"))
        self.assertEqual(out["outstanding"]["count"], 1)
        self.assertEqual(Decimal(out["outstanding"]["amount"]), Decimal("80.00"))

    def test_paid_invoices_leave_the_chase_lists(self):
        inv = self.invoice(number="INV-1", sub=self.s, total="100.00", due=date(2026, 1, 31))
        self.pay(invoice=inv, amount="100.00", on=date(2026, 1, 15))
        inv.refresh_from_db()
        out = services.summary(start=date(2026, 1, 1), end=date(2026, 1, 31), on=date(2026, 2, 1))
        self.assertEqual(out["overdue"]["count"], 0)
        self.assertEqual(out["outstanding"]["count"], 0)


class ChaseListTests(ReportingTestCase):
    def setUp(self):
        super().setUp()
        self.p = self.plan("m", Frequency.MONTHLY)
        self.s = self.sub(number="S1", plan=self.p, subtotal="100.00")

    def test_overdue_orders_oldest_due_first(self):
        a = self.invoice(number="INV-A", sub=self.s, total="100.00", due=date(2026, 1, 5))
        b = self.invoice(number="INV-B", sub=self.s, total="50.00", period_start=date(2026, 2, 1),
                         due=date(2026, 1, 1))
        rows = list(services.chase_qs(kind="overdue", on=date(2026, 2, 1)))
        self.assertEqual([r.number for r in rows], ["INV-B", "INV-A"])

    def test_older_than_days_filter(self):
        self.invoice(number="INV-A", sub=self.s, total="100.00", due=date(2026, 1, 25))
        rows = list(services.chase_qs(kind="overdue", on=date(2026, 2, 1), older_than_days=30))
        self.assertEqual(rows, [])
        rows = list(services.chase_qs(kind="overdue", on=date(2026, 2, 1), older_than_days=5))
        self.assertEqual(len(rows), 1)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            services.chase_qs(kind="shady")


class ReportingApiTests(ReportingTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.p = self.plan("m", Frequency.MONTHLY)
        self.s = self.sub(number="S1", plan=self.p, subtotal="100.00")
        self.invoice(number="INV-1", sub=self.s, total="100.00", due=date(2026, 1, 31))

    def test_staff_can_read_summary(self):
        self.client.force_authenticate(user=self.actor)
        resp = self.client.get("/api/reporting/summary/", {"start": "2026-01-01",
                                                           "end": "2026-01-31"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(Decimal(body["invoiced_total"]), Decimal("100.00"))
        self.assertIn("mrr", body)

    def test_customer_cannot_read_internal_reports(self):
        self.client.force_authenticate(user=portal(customer=self.customer))
        resp = self.client.get("/api/reporting/summary/")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get("/api/reporting/chase/", {"kind": "overdue"})
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_rejected(self):
        resp = self.client.get("/api/reporting/summary/")
        self.assertIn(resp.status_code, (401, 403))

    def test_bad_date_returns_400(self):
        self.client.force_authenticate(user=self.actor)
        resp = self.client.get("/api/reporting/summary/", {"start": "tomorrow"})
        self.assertEqual(resp.status_code, 400)

    def test_chase_pagination_pages_through(self):
        self.client.force_authenticate(user=self.actor)
        for i in range(3):
            self.invoice(number=f"INV-P{i}", sub=self.s, total=f"{i+1}.00",
                         period_start=date(2026, 2 + i, 1), due=date(2026, 1, 1))
        resp = self.client.get("/api/reporting/chase/", {"kind": "overdue", "page_size": 2,
                                                         "page": 2})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(len(body["results"]), 2)
        first_page = self.client.get("/api/reporting/chase/", {"kind": "overdue",
                                                              "page_size": 2}).json()
        self.assertNotEqual(
            {r["number"] for r in body["results"]},
            {r["number"] for r in first_page["results"]},
        )

    def test_bad_kind_rejected(self):
        self.client.force_authenticate(user=self.actor)
        resp = self.client.get("/api/reporting/chase/", {"kind": "mysterious"})
        self.assertEqual(resp.status_code, 400)


class ScalePerformanceTests(ReportingTestCase):
    """The spec's hard bar: thousands of subscriptions, every page under two seconds."""

    N = 2000

    def setUp(self):
        super().setUp()
        self.p = self.plan("m", Frequency.MONTHLY)
        customers = [Customer.objects.create(name=f"Co {i}") for i in range(5)]
        subs = [
            Subscription(
                number=f"BULK-{i:06d}", customer=customers[i % 5], plan=self.p,
                stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
                expiry_date=date(2027, 1, 1), subtotal=Decimal("100.00"),
                tax_total=Decimal("18.00"), total=Decimal("118.00"),
            )
            for i in range(self.N)
        ]
        Subscription.objects.bulk_create(subs)
        subs = list(Subscription.objects.order_by("pk"))
        invoices = [
            Invoice(
                number=f"BLK-{i:06d}", subscription=s, customer=s.customer,
                period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
                status=Invoice.Status.CONFIRMED,
                subtotal=Decimal("100.00"), tax_total=Decimal("18.00"),
                total=Decimal("118.00"), amount_paid=Decimal("0.00"),
                due_date=date(2026, 1, 20) if i % 3 == 0 else date(2026, 6, 20),
            )
            for i, s in enumerate(subs)
        ]
        Invoice.objects.bulk_create(invoices)

    def test_summary_completes_within_budget_and_query_ceiling(self):
        with CaptureQueriesContext(connection) as ctx:
            started = time.monotonic()
            out = services.summary(start=date(2026, 1, 1), end=date(2026, 1, 31),
                                   on=date(2026, 2, 1))
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.0, f"summary took {elapsed:.2f}s with {self.N} subs")
        # every aggregate stays in SQL: a bounded number of queries, not one per row
        self.assertLessEqual(len(ctx.captured_queries), 12)
        self.assertEqual(out["active_subscriptions"], self.N)
        self.assertEqual(out["overdue"]["count"], self.N // 3 + (1 if self.N % 3 else 0))

    def test_chase_list_stays_bounded_at_scale(self):
        with CaptureQueriesContext(connection) as ctx:
            started = time.monotonic()
            qs = services.chase_qs(kind="overdue", on=date(2026, 2, 1))
            total = qs.count()
            page = list(qs[:50])
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.0, f"chase took {elapsed:.2f}s")
        self.assertEqual(len(page), 50)
        self.assertGreater(total, 600)
        # select_related keeps it to two queries (count + slice), no per-row fetches
        self.assertLessEqual(len(ctx.captured_queries), 4)


class ExpiredTermTests(ReportingTestCase):
    """MRR must not count contracts whose term has already ended."""

    def test_ended_terms_are_not_active_and_carry_no_mrr(self):
        monthly = self.plan("m", Frequency.MONTHLY)
        live = self.sub(number="S1", plan=monthly, subtotal="100.00")
        ended = self.sub(number="S2", plan=monthly, subtotal="200.00")
        # `live` keeps its 2027 expiry; `ended` lapsed before the as-of date.
        self.assertTrue(live.pk)
        Subscription.objects.filter(pk=ended.pk).update(expiry_date=date(2026, 2, 1))

        out = services.summary(on=date(2026, 10, 31))

        self.assertEqual(out["active_subscriptions"], 1)
        self.assertEqual(Decimal(out["mrr"]), Decimal("100.00"))
        self.assertEqual(Decimal(out["arr"]), Decimal("1200.00"))

    def test_paused_count_ignores_ended_terms(self):
        monthly = self.plan("m", Frequency.MONTHLY)
        paused_live = self.sub(number="S1", plan=monthly, subtotal="100.00", paused=True)
        paused_ended = self.sub(number="S2", plan=monthly, subtotal="100.00", paused=True)
        Subscription.objects.filter(pk=paused_ended.pk).update(expiry_date=date(2026, 2, 1))

        out = services.summary(on=date(2026, 10, 31))

        self.assertEqual(out["paused_subscriptions"], 1)
        self.assertTrue(paused_live.pk)


class ExpiringRenewalQueueTests(ReportingTestCase):
    """The renewal queue: the spec's 'renewals get missed' has a list now."""

    def setUp(self):
        super().setUp()
        self.plan = self.plan("Monthly", Frequency.MONTHLY)

    def test_only_terms_ending_inside_the_horizon_are_listed(self):
        soon = self.sub(number="SUB-1", plan=self.plan, subtotal="100.00")
        soon.expiry_date = date(2026, 1, 20)
        soon.save(update_fields=["expiry_date"])
        far = self.sub(number="SUB-2", plan=self.plan, subtotal="100.00")
        far.expiry_date = date(2026, 9, 1)
        far.save(update_fields=["expiry_date"])

        body = services.expiring_qs(within_days=30, on=date(2026, 1, 1))
        self.assertEqual([s.number for s in body], ["SUB-1"])

    def test_paused_and_closed_terms_are_not_renewals(self):
        paused = self.sub(number="SUB-3", plan=self.plan, subtotal="100.00", paused=True)
        paused.expiry_date = date(2026, 1, 10)
        paused.save(update_fields=["expiry_date"])
        closed = self.sub(number="SUB-4", plan=self.plan, subtotal="100.00",
                          stage=Subscription.Stage.CLOSED)
        closed.expiry_date = date(2026, 1, 11)
        closed.save(update_fields=["expiry_date"])

        self.assertEqual(services.expiring_qs(within_days=30, on=date(2026, 1, 1)).count(), 0)

    def test_endpoint_is_staff_only_and_reports_the_horizon(self):
        sub = self.sub(number="SUB-5", plan=self.plan, subtotal="100.00")
        sub.expiry_date = date(2026, 1, 15)
        sub.save(update_fields=["expiry_date"])

        client = APIClient()
        client.force_authenticate(self.actor)
        response = client.get("/api/reporting/expiring/?within_days=30&as_of=2026-01-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["within_days"], 30)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["results"][0]["number"], "SUB-5")

        portal_user = portal(customer=self.customer)
        client.force_authenticate(portal_user)
        self.assertEqual(
            client.get("/api/reporting/expiring/").status_code, 403
        )
