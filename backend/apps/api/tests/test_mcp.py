import json
import threading
import urllib.error
import urllib.request
from datetime import date

from django.test import TestCase

from apps.api.tests.helpers import ApiTestCase
from apps.billing.models import Invoice
from apps.subscriptions.models import Subscription
from mcp_server.__main__ import resolve_actor
from mcp_server.http_transport import build_http_server
from mcp_server.protocol import McpServer, ServerContext
from mcp_server.tools import build_tools


def make_server(actor, read_only=False):
    return McpServer(
        context=ServerContext(actor=actor, read_only=read_only),
        tools=build_tools(),
    )


def call(server, name, arguments=None):
    return server.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })


def payload(response):
    """Decode the JSON text a tool returned (or raise with the error text)."""
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


class ProtocolTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.staff)

    def test_initialize_handshake(self):
        response = self.server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}},
        })
        result = response["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "brightloop")

    def test_unknown_protocol_version_falls_back(self):
        response = self.server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "1999-01-01"},
        })
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")

    def test_notifications_get_no_response(self):
        self.assertIsNone(self.server.handle_message({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }))

    def test_tools_list_is_complete_and_typed(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        tools = response["result"]["tools"]
        names = {tool["name"] for tool in tools}
        expected = {
            "whoami", "list_customers", "get_customer", "list_products", "list_plans",
            "list_tax_rules", "list_subscriptions", "get_subscription",
            "create_subscription", "add_subscription_line",
            "remove_subscription_line", "subscription_transition",
            "preview_billing_day", "run_billing_day", "list_invoices", "get_invoice",
            "invoice_action", "record_payment", "remove_payment",
            "list_discount_rules", "create_discount_rule", "deactivate_discount_rule",
            "reporting_summary", "reporting_chase", "list_billing_runs",
        }
        self.assertTrue(expected <= names, f"missing: {expected - names}")
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(tool["description"])
            self.assertIn("readOnlyHint", tool["annotations"])

    def test_unknown_tool_is_a_jsonrpc_error(self):
        response = call(self.server, "no_such_tool")
        self.assertEqual(response["error"]["code"], -32602)

    def test_unknown_method_is_a_jsonrpc_error(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 3, "method": "resources/list"}
        )
        self.assertEqual(response["error"]["code"], -32601)

    def test_parse_error(self):
        response = self.server.handle_line("{not json")
        self.assertEqual(response["error"]["code"], -32700)

    def test_batch_requests_are_answered_in_order(self):
        batch = json.dumps([
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        responses = self.server.handle_line(batch)
        self.assertEqual([r["id"] for r in responses], [1, 2])


class ActorTests(ApiTestCase):
    def test_whoami_reports_role_and_read_only(self):
        server = make_server(self.staff, read_only=True)
        body = payload(call(server, "whoami"))
        self.assertEqual(body["email"], self.staff.email)
        self.assertEqual(body["role"], "staff")
        self.assertTrue(body["read_only"])
        self.assertFalse(body["capabilities"]["can_admin"])

    def test_resolve_actor_rejects_the_portal(self):
        with self.assertRaises(SystemExit):
            resolve_actor(self.customer_user.email)

    def test_resolve_actor_defaults_to_an_admin(self):
        self.assertEqual(resolve_actor(None), self.admin)

    def test_resolve_actor_by_email(self):
        self.assertEqual(resolve_actor(self.staff.email), self.staff)


class ReadToolTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.staff)
        self.plan = self.make_plan()
        self.product = self.plan.product

    def test_list_plans_and_selectable_filter(self):
        self.make_plan(name="Expired", start=date(2020, 1, 1), end=date(2021, 1, 1))
        body = payload(call(self.server, "list_plans", {"selectable_only": True}))
        names = [row["name"] for row in body["results"]]
        self.assertEqual(names, ["Monthly"])

    def test_list_customers_and_search(self):
        body = payload(call(self.server, "list_customers", {"q": "shire"}))
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["name"], "Shire Logistics")

    def test_get_subscription_by_number(self):
        subscription = Subscription.objects.create(
            number="SUB-2026-000042", customer=self.customer, plan=self.plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2027, 1, 1),
        )
        body = payload(call(self.server, "get_subscription",
                            {"subscription": "SUB-2026-000042"}))
        self.assertEqual(body["id"], subscription.id)
        self.assertEqual(body["plan_name"], "Monthly")

    def test_missing_subscription_is_a_tool_error(self):
        response = call(self.server, "get_subscription", {"subscription": "SUB-1999-1"})
        self.assertTrue(response["result"]["isError"])

    def test_reporting_summary_runs(self):
        body = payload(call(self.server, "reporting_summary",
                            {"start": "2026-01-01", "end": "2026-01-31"}))
        self.assertIn("mrr", body)
        self.assertEqual(body["window"]["start"], "2026-01-01")


class WriteToolTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.staff)
        self.plan = self.make_plan()
        self.product = self.plan.product
        self.tax = self.make_tax()

    def create_subscription(self):
        response = call(self.server, "create_subscription", {
            "customer_id": self.customer.id,
            "plan_id": self.plan.id,
            "start_date": "2026-11-01",
            "expiry_date": "2027-02-01",
            "lines": [{"product_id": self.product.id, "quantity": 1,
                       "tax_rule_id": self.tax.id}],
        })
        self.assertFalse(response["result"]["isError"], response)
        return payload(response)

    def test_create_subscription_with_lines(self):
        body = self.create_subscription()
        self.assertTrue(body["number"].startswith("SUB-"))
        self.assertEqual(body["line_count"] if "line_count" in body else len(body["lines"]), 1)
        self.assertEqual(body["total"], "118.00")

    def test_full_lifecycle_through_tools(self):
        subscription = self.create_subscription()
        for action, stage in [("send_quotation", "quotation"),
                              ("confirm", "confirmed"),
                              ("activate", "active")]:
            response = call(self.server, "subscription_transition",
                            {"subscription": subscription["number"], "action": action})
            self.assertFalse(response["result"]["isError"], response)
            self.assertEqual(payload(response)["stage"], stage)
        paused = payload(call(self.server, "subscription_transition",
                              {"subscription": subscription["number"],
                               "action": "pause"}))
        self.assertTrue(paused["is_paused"])

    def test_invalid_transition_is_reported_not_crashed(self):
        subscription = self.create_subscription()
        response = call(self.server, "subscription_transition",
                        {"subscription": subscription["number"], "action": "confirm"})
        self.assertTrue(response["result"]["isError"])
        self.assertIn("invalid_transition", response["result"]["content"][0]["text"])

    def test_remove_line_and_recompute(self):
        subscription = self.create_subscription()
        line_id = subscription["lines"][0]["id"]
        body = payload(call(self.server, "remove_subscription_line",
                            {"subscription": subscription["number"], "line_id": line_id}))
        self.assertEqual(body["lines"], [])
        self.assertEqual(body["total"], "0.00")

    def test_billing_dry_run_then_confirm(self):
        subscription = self.create_subscription()
        for action in ("send_quotation", "confirm", "activate"):
            call(self.server, "subscription_transition",
                 {"subscription": subscription["number"], "action": action})

        preview = payload(call(self.server, "run_billing_day",
                               {"on": "2026-11-15"}))
        self.assertFalse(preview["executed"])
        self.assertEqual(preview["preview"]["invoices"], 1)
        self.assertEqual(Invoice.objects.count(), 0)

        result = payload(call(self.server, "run_billing_day",
                              {"on": "2026-11-15", "confirm": True}))
        self.assertTrue(result["executed"])
        self.assertEqual(result["billed_count"], 1)
        self.assertEqual(Invoice.objects.count(), 1)

        again = payload(call(self.server, "run_billing_day",
                             {"on": "2026-11-15", "confirm": True}))
        self.assertEqual(again["billed_count"], 0)

    def test_sweep_dry_run_then_confirm(self):
        """The per-plan auto-close switch needs a reachable trigger."""
        subscription = self.create_subscription()
        for action in ("send_quotation", "confirm", "activate"):
            call(self.server, "subscription_transition",
                 {"subscription": subscription["number"], "action": action})
        Subscription.objects.filter(number=subscription["number"]).update(
            start_date=date(2026, 1, 1), expiry_date=date(2026, 2, 1)
        )
        self.plan.auto_close_on_expiry = True
        self.plan.save(update_fields=["auto_close_on_expiry"])

        preview = payload(call(self.server, "sweep_expired_subscriptions",
                               {"on": "2026-03-01"}))
        self.assertFalse(preview["executed"])
        self.assertEqual(preview["would_close"], [subscription["number"]])
        self.assertEqual(
            Subscription.objects.get(number=subscription["number"]).stage,
            Subscription.Stage.ACTIVE,
        )

        result = payload(call(self.server, "sweep_expired_subscriptions",
                              {"on": "2026-03-01", "confirm": True}))
        self.assertTrue(result["executed"])
        self.assertEqual(result["closed"], [subscription["number"]])
        self.assertEqual(
            Subscription.objects.get(number=subscription["number"]).stage,
            Subscription.Stage.CLOSED,
        )

    def test_payment_flow(self):
        subscription = self.create_subscription()
        for action in ("send_quotation", "confirm", "activate"):
            call(self.server, "subscription_transition",
                 {"subscription": subscription["number"], "action": action})
        payload(call(self.server, "run_billing_day",
                     {"on": "2026-11-15", "confirm": True}))
        invoice = Invoice.objects.get()

        confirmed = payload(call(self.server, "invoice_action",
                                 {"invoice": invoice.number, "action": "confirm"}))
        self.assertEqual(confirmed["status"], "confirmed")

        paid = payload(call(self.server, "record_payment", {
            "invoice": invoice.number, "amount": "118.00", "method": "card",
        }))
        self.assertEqual(paid["invoice"]["status"], "paid")
        self.assertEqual(paid["invoice"]["amount_due"], "0.00")

    def test_read_only_mode_refuses_writes(self):
        server = make_server(self.staff, read_only=True)
        response = call(server, "create_subscription", {
            "customer_id": self.customer.id, "plan_id": self.plan.id,
            "start_date": "2026-11-01",
        })
        self.assertTrue(response["result"]["isError"])
        self.assertIn("read-only", response["result"]["content"][0]["text"])
        self.assertEqual(Subscription.objects.count(), 0)

    def test_staff_cannot_create_discount_rules_but_admin_can(self):
        rule = {"name": "Launch", "scope": "product", "kind": "percent",
                "value": "10.00", "applies_from": "2026-01-01"}
        denied = call(self.server, "create_discount_rule", rule)
        self.assertTrue(denied["result"]["isError"])
        self.assertIn("admin", denied["result"]["content"][0]["text"].lower())

        allowed = call(make_server(self.admin), "create_discount_rule", rule)
        self.assertFalse(allowed["result"]["isError"], allowed)
        self.assertEqual(payload(allowed)["value"], "10.00")


class HttpTransportTests(ApiTestCase):
    def start(self, token=None):
        server = make_server(self.staff)
        httpd = build_http_server(mcp=server, host="127.0.0.1", port=0, token=token)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def post(self, port, body, token=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {token}"} if token else {})},
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=5)

    def test_initialize_over_http(self):
        port = self.start()
        with self.post(port, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-06-18"}}) as response:
            self.assertEqual(response.status, 200)
            body = json.loads(response.read())
        self.assertEqual(body["result"]["serverInfo"]["name"], "brightloop")

    def test_token_is_enforced(self):
        port = self.start(token="s3cret")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post(port, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(ctx.exception.code, 401)

        with self.post(port, {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                       token="s3cret") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["result"], {})

    def test_notification_returns_202(self):
        port = self.start()
        with self.post(port, {"jsonrpc": "2.0",
                              "method": "notifications/initialized"}) as response:
            self.assertEqual(response.status, 202)


class HttpFailClosedTests(TestCase):
    """
    The HTTP transport used to accept everyone when no token was configured.
    Bind it to 0.0.0.0 and every network peer became the configured actor.
    """

    def test_non_loopback_bind_without_a_token_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            build_http_server(mcp=None, host="0.0.0.0", port=0)
        self.assertIn("token", str(ctx.exception).lower())

    def test_loopback_bind_without_a_token_is_allowed(self):
        httpd = build_http_server(mcp=None, host="127.0.0.1", port=0)
        try:
            self.assertIsNone(httpd.token)
        finally:
            httpd.server_close()

    def test_any_bind_with_a_token_is_allowed(self):
        httpd = build_http_server(mcp=None, host="0.0.0.0", port=0, token="s3cret")
        try:
            self.assertEqual(httpd.token, "s3cret")
        finally:
            httpd.server_close()
