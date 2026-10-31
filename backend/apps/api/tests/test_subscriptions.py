from datetime import date
from decimal import Decimal

from apps.api.tests.helpers import ApiTestCase
from apps.subscriptions.models import Subscription


class SubscriptionCreationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.staff)
        self.product = self.make_product()
        self.plan = self.make_plan(product=self.product)
        self.tax = self.make_tax()

    def create(self, **overrides):
        payload = {
            "customer": self.customer.id,
            "plan": self.plan.id,
            "start_date": "2026-01-01",
            "lines": [
                {"product": self.product.id, "quantity": 2, "tax_rule": self.tax.id}
            ],
        }
        payload.update(overrides)
        return self.client.post("/api/subscriptions/", payload, format="json")

    def test_create_with_lines_computes_totals(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["number"].startswith("SUB-"))
        self.assertEqual(body["stage"], "draft")
        self.assertEqual(body["subtotal"], "200.00")
        self.assertEqual(body["tax_total"], "36.00")
        self.assertEqual(body["total"], "236.00")
        self.assertEqual(len(body["lines"]), 1)

    def test_expiry_defaults_to_one_period(self):
        body = self.create().json()
        self.assertEqual(body["start_date"], "2026-01-01")
        self.assertEqual(body["expiry_date"], "2026-02-01")

    def test_unselectable_plan_is_refused(self):
        archived = self.make_plan(name="Archived", start=date(2020, 1, 1), end=date(2021, 1, 1))
        response = self.create(plan=archived.id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("plan", response.json()["errors"])

    def test_expiry_before_start_is_refused(self):
        response = self.create(expiry_date="2025-12-01")
        self.assertEqual(response.status_code, 400)
        self.assertIn("expiry_date", response.json()["errors"])

    def test_line_below_plan_minimum_is_refused(self):
        strict = self.make_plan(name="Strict", minimum=3)
        response = self.create(
            plan=strict.id,
            lines=[{"product": self.product.id, "quantity": 1}],
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.json()["errors"])

    def test_variant_from_another_product_is_refused(self):
        other = self.make_product(name="Other")
        from apps.products.models import ProductVariant
        foreign = ProductVariant.objects.create(
            product=other, attribute="brand", value="X", price_delta=Decimal("0.00")
        )
        response = self.create(lines=[{
            "product": self.product.id, "variant": foreign.id, "quantity": 1,
        }])
        self.assertEqual(response.status_code, 400)
        self.assertIn("variant", response.json()["errors"]["lines"][0])

    def test_template_must_match_the_plan(self):
        from apps.quotations.models import QuotationTemplate
        other_plan = self.make_plan(name="Yearly", frequency="yearly")
        template = QuotationTemplate.objects.create(
            name="Yearly deal", plan=other_plan, validity_days=14
        )
        response = self.create(origin_template=template.id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("origin_template", response.json()["errors"])


class SubscriptionLifecycleTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.staff)
        self.product = self.make_product()
        self.plan = self.make_plan(product=self.product)
        self.sub = self.client.post("/api/subscriptions/", {
            "customer": self.customer.id, "plan": self.plan.id,
            "start_date": "2026-01-01",
            "lines": [{"product": self.product.id, "quantity": 1}],
        }, format="json").json()
        self.base = f"/api/subscriptions/{self.sub['id']}"

    def act(self, action, **body):
        return self.client.post(f"{self.base}/{action}/", body, format="json")

    def test_happy_path_draft_to_active_to_closed(self):
        response = self.act("send-quotation")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stage"], "quotation")
        self.assertIsNotNone(response.json()["validity_until"])

        response = self.act("confirm")
        self.assertEqual(response.json()["stage"], "confirmed")

        response = self.act("activate")
        self.assertEqual(response.json()["stage"], "active")

        response = self.act("close", reason="Contract ended")
        self.assertEqual(response.json()["stage"], "closed")
        self.assertEqual(response.json()["closed_reason"], "Contract ended")

    def test_backward_or_skipped_transitions_are_409(self):
        response = self.act("confirm")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "invalid_transition")

        response = self.act("activate")
        self.assertEqual(response.status_code, 409)

    def test_quotation_requires_lines(self):
        empty = self.client.post("/api/subscriptions/", {
            "customer": self.customer.id, "plan": self.plan.id,
            "start_date": "2026-01-01",
        }, format="json").json()
        response = self.client.post(
            f"/api/subscriptions/{empty['id']}/send-quotation/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("lines", response.json()["errors"])

    def test_pause_and_resume_only_while_active(self):
        self.assertEqual(self.act("pause").status_code, 409)  # still draft
        self.act("send-quotation")
        self.act("confirm")
        self.act("activate")
        paused = self.act("pause")
        self.assertEqual(paused.status_code, 200)
        self.assertTrue(paused.json()["is_paused"])
        resumed = self.act("resume")
        self.assertFalse(resumed.json()["is_paused"])

    def test_renew_extends_the_term_by_one_period(self):
        self.act("send-quotation")
        self.act("confirm")
        activated = self.act("activate").json()
        self.assertEqual(activated["expiry_date"], "2026-02-01")
        renewed = self.act("renew").json()
        self.assertEqual(renewed["expiry_date"], "2026-03-01")

    def test_early_close_honours_the_plan_flag(self):
        strict = self.make_plan(name="Locked", frequency="yearly")
        strict.allow_early_close = False
        strict.save(update_fields=["allow_early_close"])
        created = self.client.post("/api/subscriptions/", {
            "customer": self.customer.id, "plan": strict.id,
            "start_date": "2026-01-01",
            "lines": [{"product": self.product.id, "quantity": 1}],
        }, format="json").json()
        base = f"/api/subscriptions/{created['id']}"
        self.client.post(f"{base}/send-quotation/")
        self.client.post(f"{base}/confirm/")
        self.client.post(f"{base}/activate/")
        response = self.client.post(f"{base}/close/", {"reason": "Too early"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("early closure", response.json()["errors"]["stage"][0])

    def test_lines_are_immutable_once_confirmed(self):
        self.act("send-quotation")
        self.act("confirm")
        response = self.client.post(f"{self.base}/lines/", {
            "product": self.product.id, "quantity": 1,
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_remove_line_recalculates_totals(self):
        line_id = self.sub["lines"][0]["id"]
        response = self.client.delete(f"{self.base}/lines/{line_id}/")
        self.assertEqual(response.status_code, 204)
        detail = self.client.get(f"{self.base}/").json()
        self.assertEqual(detail["total"], "0.00")
        self.assertEqual(detail["lines"], [])

    def test_removing_an_unknown_line_is_400(self):
        response = self.client.delete(f"{self.base}/lines/999999/")
        self.assertEqual(response.status_code, 400)

    def test_add_line_updates_totals(self):
        extra = self.make_product("Extra Seat", price="100.00")
        response = self.client.post(f"{self.base}/lines/", {
            "product": extra.id, "quantity": 3, "tax_rule": self.make_tax().id,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        detail = self.client.get(f"{self.base}/").json()
        self.assertEqual(detail["subtotal"], "400.00")  # 1x100 + 3x100

    def test_same_product_twice_on_one_subscription_conflicts(self):
        response = self.client.post(f"{self.base}/lines/", {
            "product": self.product.id, "quantity": 1,
        }, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "conflict")

    def test_customer_filter_and_stage_filter(self):
        response = self.client.get("/api/subscriptions/", {"stage": "draft"})
        self.assertEqual(response.json()["count"], 1)
        response = self.client.get(
            "/api/subscriptions/", {"customer": self.other_customer.id}
        )
        self.assertEqual(response.json()["count"], 0)

    def test_portal_reads_its_own_subscription(self):
        self.auth(self.customer_user)
        response = self.client.get(f"{self.base}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["number"], self.sub["number"])

    def test_number_series_does_not_reuse_numbers(self):
        second = self.client.post("/api/subscriptions/", {
            "customer": self.customer.id, "plan": self.plan.id,
            "start_date": "2026-01-01",
            "lines": [{"product": self.product.id, "quantity": 1}],
        }, format="json").json()
        self.assertNotEqual(second["number"], self.sub["number"])
        self.assertEqual(Subscription.objects.count(), 2)
