"""
Pagination must be deterministic.

`annotate(Count(...))` adds GROUP BY, which silently drops the model's
Meta.ordering. Unordered pages can repeat or skip rows, so a finance lead
paging through invoices sees a different set every time and never knows.
"""

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.api.tests.helpers import ApiTestCase
from apps.billing.models import BillingRun
from apps.subscriptions.models import Subscription


class OrderedPaginationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.plan = self.make_plan()
        for i in range(5):
            Subscription.objects.create(
                number=f"SUB-2026-{i:06d}", customer=self.customer, plan=self.plan,
                stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
                expiry_date=date(2027, 1, 1), subtotal=Decimal("100.00"),
                tax_total=Decimal("18.00"), total=Decimal("118.00"),
            )
        self.auth(self.staff)

    def _order_by_clause(self, path):
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(path, {"page_size": 2})
        statements = [
            query["sql"] for query in ctx.captured_queries
            if "ORDER BY" in query["sql"].upper()
        ]
        self.assertTrue(statements, f"{path}: list query carries no ORDER BY")
        return statements[0].upper()

    def test_subscription_list_is_explicitly_ordered(self):
        statement = self._order_by_clause("/api/subscriptions/")
        self.assertIn("SUBSCRIPTIONS_SUBSCRIPTION", statement)
        self.assertIn("ORDER BY", statement)

    def test_billing_run_list_is_explicitly_ordered(self):
        BillingRun.objects.create(ran_on=date(2026, 1, 5))
        BillingRun.objects.create(ran_on=date(2026, 1, 6))
        statement = self._order_by_clause("/api/billing-runs/")
        self.assertIn("BILLING_BILLINGRUN", statement)

    def test_paging_returns_every_row_exactly_once(self):
        seen = []
        for page in (1, 2, 3):
            body = self.client.get(
                "/api/subscriptions/", {"page": page, "page_size": 2}
            ).json()
            seen.extend(row["id"] for row in body["results"])
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(set(seen)), 5)
