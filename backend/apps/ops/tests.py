from unittest.mock import patch

from django.test import override_settings

from apps.api.tests.helpers import ApiTestCase
from apps.billing.models import Invoice
from apps.customers.models import Customer
from apps.subscriptions.models import Subscription


class OpsAccessTests(ApiTestCase):
    """The developer console is admin-only and off outside DEBUG by default."""

    def test_disabled_ops_tools_answer_404_even_for_an_admin(self):
        with override_settings(OPS_TOOLS_ENABLED=False):
            self.auth(self.admin)
            self.assertEqual(
                self.client.get("/api/ops/overview/").status_code, 404
            )

    def test_staff_may_not_use_the_ops_surface(self):
        self.auth(self.staff)
        self.assertEqual(self.client.get("/api/ops/overview/").status_code, 403)

    def test_anonymous_gets_nothing(self):
        self.anonymous()
        self.assertIn(
            self.client.get("/api/ops/overview/").status_code, (401, 403)
        )

    def test_admin_reads_the_overview(self):
        self.auth(self.admin)
        body = self.client.get("/api/ops/overview/").json()
        self.assertEqual(body["database"]["engine"], "postgresql")
        self.assertIn("counts", body)
        self.assertGreaterEqual(body["migrations"]["applied"], 1)
        self.assertTrue(body["ops_enabled"])


class OpsDataTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.admin)

    def test_migrations_endpoint_reports_applied_and_pending(self):
        body = self.client.get("/api/ops/migrations/").json()
        apps = {row["app"]: row for row in body["apps"]}
        self.assertIn("subscriptions", apps)
        applied = [item["name"] for item in apps["subscriptions"]["applied"]]
        self.assertIn("0003_pauseperiod", applied)
        self.assertEqual(apps["subscriptions"]["pending"], [])

    def test_apply_migrations_runs_migrate(self):
        with patch("apps.ops.services.call_command") as migrate:
            response = self.client.post("/api/ops/migrations/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(migrate.call_args.args[0], "migrate")
        self.assertFalse(migrate.call_args.kwargs["interactive"])

    def test_tables_endpoint_counts_rows_and_size(self):
        Customer.objects.create(name="Table probe")
        body = self.client.get("/api/ops/tables/").json()
        rows = {row["table"]: row for row in body["tables"]}
        self.assertGreaterEqual(rows["customers_customer"]["rows"], 1)
        self.assertGreater(rows["customers_customer"]["bytes"], 0)

    def test_logs_record_requests_and_the_sql_they_ran(self):
        self.client.get("/api/customers/")
        body = self.client.get("/api/ops/logs/").json()
        paths = [row["path"] for row in body["requests"]]
        self.assertIn("/api/customers/", paths)
        self.assertTrue(body["sql"])
        self.assertTrue(all("sql" in row and "ms" in row for row in body["sql"]))

    def test_clear_empties_the_buffers(self):
        self.client.get("/api/customers/")
        self.assertEqual(self.client.delete("/api/ops/logs/").status_code, 204)
        body = self.client.get("/api/ops/logs/").json()
        # Only the logs call that followed the clear is recorded.
        self.assertLessEqual(len(body["requests"]), 1)

    def test_demo_data_seeds_a_billable_tenant_once(self):
        first = self.client.post("/api/ops/demo-data/", {})
        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.json()["already_present"])
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(
            Subscription.objects.filter(stage=Subscription.Stage.ACTIVE).count(), 2
        )
        self.assertTrue(
            Subscription.objects.filter(is_paused=True).exists()
        )

        before = Subscription.objects.count()
        second = self.client.post("/api/ops/demo-data/", {})
        self.assertTrue(second.json()["already_present"])
        self.assertEqual(Subscription.objects.count(), before)
