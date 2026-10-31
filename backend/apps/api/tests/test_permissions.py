from datetime import date
from decimal import Decimal

from apps.api.tests.helpers import ApiTestCase
from apps.billing.models import DiscountRule, TaxRule
from apps.customers.models import Customer
from apps.products.models import Plan, Product
from apps.subscriptions.models import Subscription


class AuthenticationGateTests(ApiTestCase):
    def test_every_resource_requires_a_token(self):
        for url in ["/api/customers/", "/api/subscriptions/", "/api/invoices/",
                    "/api/products/", "/api/plans/", "/api/users/",
                    "/api/billing-runs/", "/api/discount-rules/"]:
            with self.subTest(url=url):
                self.assertEqual(self.anonymous().get(url).status_code, 401)

    def test_health_check_stays_public(self):
        self.assertEqual(self.anonymous().get("/api/health/").status_code, 200)


class PortalScopingTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.plan = self.make_plan()
        self.mine = Subscription.objects.create(
            number="SUB-2026-000001", customer=self.customer, plan=self.plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2027, 1, 1), subtotal=Decimal("100.00"),
            tax_total=Decimal("18.00"), total=Decimal("118.00"),
        )
        self.theirs = Subscription.objects.create(
            number="SUB-2026-000002", customer=self.other_customer, plan=self.plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2027, 1, 1), subtotal=Decimal("100.00"),
            tax_total=Decimal("18.00"), total=Decimal("118.00"),
        )

    def test_portal_lists_only_its_own_subscriptions(self):
        response = self.auth(self.customer_user).get("/api/subscriptions/")
        self.assertEqual(response.status_code, 200)
        numbers = [row["number"] for row in response.json()["results"]]
        self.assertEqual(numbers, ["SUB-2026-000001"])

    def test_foreign_subscription_is_a_404_not_a_403(self):
        response = self.auth(self.customer_user).get(
            f"/api/subscriptions/{self.theirs.id}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_portal_cannot_mutate_a_subscription(self):
        url = f"/api/subscriptions/{self.mine.id}/close/"
        self.assertEqual(self.auth(self.customer_user).post(url).status_code, 403)

    def test_portal_cannot_create_subscriptions(self):
        response = self.auth(self.customer_user).post("/api/subscriptions/", {
            "customer": self.customer.id, "plan": self.plan.id,
            "start_date": "2026-01-01",
        })
        self.assertEqual(response.status_code, 403)

    def test_portal_sees_only_its_own_customer_record(self):
        response = self.auth(self.customer_user).get("/api/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["id"], self.customer.id)

    def test_portal_cannot_list_tax_rules(self):
        self.auth(self.customer_user)
        self.assertEqual(self.client.get("/api/tax-rules/").status_code, 403)

    def test_portal_cannot_read_the_payment_ledger(self):
        self.auth(self.customer_user)
        self.assertEqual(self.client.get("/api/payments/").status_code, 403)

    def test_portal_cannot_run_billing(self):
        self.auth(self.customer_user)
        self.assertEqual(
            self.client.post("/api/billing-runs/run/", {"dry_run": True}).status_code,
            403,
        )


class RoleBoundaryTests(ApiTestCase):
    def test_staff_cannot_create_catalog_but_admin_can(self):
        payload = {"name": "Widget", "type": "goods",
                   "sales_price": "10.00", "cost_price": "4.00"}
        self.assertEqual(
            self.auth(self.staff).post("/api/products/", payload).status_code, 403
        )
        response = self.auth(self.admin).post("/api/products/", payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Product.objects.count(), 1)

    def test_staff_cannot_create_plans(self):
        product = self.make_product()
        payload = {
            "product": product.id, "name": "Monthly", "billing_frequency": "monthly",
            "price": "100.00", "minimum_quantity": 1,
            "availability_start": "2025-01-01",
        }
        self.assertEqual(
            self.auth(self.staff).post("/api/plans/", payload).status_code, 403
        )
        response = self.auth(self.admin).post("/api/plans/", payload)
        self.assertEqual(response.status_code, 201)

    def test_staff_may_read_plans_and_tax_rules(self):
        self.make_plan()
        TaxRule.objects.create(name="GST", rate=Decimal("18.00"))
        client = self.auth(self.staff)
        self.assertEqual(client.get("/api/plans/").status_code, 200)
        self.assertEqual(client.get("/api/tax-rules/").status_code, 200)

    def test_staff_cannot_change_tax_rules(self):
        self.auth(self.staff)
        response = self.client.post("/api/tax-rules/", {"name": "VAT", "rate": "5.00"})
        self.assertEqual(response.status_code, 403)

    def test_only_admin_creates_discount_rules(self):
        payload = {
            "name": "Launch", "scope": "product", "kind": "percent",
            "value": "10.00", "applies_from": "2026-01-01",
        }
        self.assertEqual(
            self.auth(self.staff).post("/api/discount-rules/", payload).status_code, 403
        )
        self.assertEqual(
            self.auth(self.admin).post("/api/discount-rules/", payload).status_code, 201
        )
        self.assertEqual(DiscountRule.objects.count(), 1)

    def test_staff_manage_customers(self):
        response = self.auth(self.staff).post("/api/customers/", {"name": "Rohan Ltd"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Customer.objects.filter(name="Rohan Ltd").count(), 1)

    def test_staff_manage_quotation_templates(self):
        plan = self.make_plan()
        response = self.auth(self.staff).post("/api/quotation-templates/", {
            "name": "Standard", "plan": plan.id, "validity_days": 14,
            "lines": [{"product": plan.product_id, "quantity": 2}],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["lines"][0]["unit_price"], "100.00")

    def test_staff_can_edit_a_subscription_in_place(self):
        self.make_plan()
        created = self.auth(self.staff).post("/api/subscriptions/", {
            "customer": self.customer.id, "plan": Plan.objects.first().id,
            "start_date": "2026-01-01",
        }).json()
        response = self.client.patch(
            f"/api/subscriptions/{created['id']}/", {"payment_terms_days": 45},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payment_terms_days"], 45)

    def test_subscription_patch_rejects_unknown_fields(self):
        self.make_plan()
        created = self.auth(self.staff).post("/api/subscriptions/", {
            "customer": self.customer.id, "plan": Plan.objects.first().id,
            "start_date": "2026-01-01",
        }).json()
        response = self.client.patch(
            f"/api/subscriptions/{created['id']}/", {"stage": "active"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_deactivated_user_is_locked_out(self):
        from rest_framework.test import APIClient

        from apps.api.tests.helpers import PASSWORD

        client = APIClient()
        tokens = client.post(
            "/api/auth/token/", {"email": self.staff.email, "password": PASSWORD}
        ).json()
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        # JWT authentication re-reads the user row: a deactivated account is 401.
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(client.get("/api/subscriptions/").status_code, 401)
