from datetime import date, timedelta
from decimal import Decimal

from apps.api.tests.helpers import ApiTestCase
from apps.products.models import Plan, Product, ProductVariant


class ProductApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.admin)

    def test_create_product_with_variants(self):
        response = self.client.post("/api/products/", {
            "name": "CRM Suite",
            "type": "service",
            "sales_price": "100.00",
            "cost_price": "40.00",
            "variants": [
                {"attribute": "brand", "value": "Odoo", "price_delta": "560.00"},
                {"attribute": "brand", "value": "Community", "price_delta": "0.00"},
            ],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        prices = {v["value"]: v["effective_price"] for v in body["variants"]}
        self.assertEqual(prices, {"Odoo": "660.00", "Community": "100.00"})

    def test_variant_may_not_drive_the_price_negative(self):
        response = self.client.post("/api/products/", {
            "name": "Budget", "type": "good", "sales_price": "10.00",
            "cost_price": "1.00",
            "variants": [{"attribute": "size", "value": "tiny", "price_delta": "-11.00"}],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Product.objects.count(), 0)

    def test_omitting_a_variant_retires_it_without_losing_history(self):
        product = Product.objects.create(
            name="Widget", sales_price=Decimal("10.00"), cost_price=Decimal("1.00")
        )
        keep = ProductVariant.objects.create(
            product=product, attribute="brand", value="Keep", price_delta=Decimal("0.00")
        )
        drop = ProductVariant.objects.create(
            product=product, attribute="brand", value="Drop", price_delta=Decimal("0.00")
        )
        response = self.client.patch(f"/api/products/{product.id}/", {
            "variants": [{"attribute": "brand", "value": "Keep", "price_delta": "2.00"}],
        }, format="json")
        self.assertEqual(response.status_code, 200)
        keep.refresh_from_db()
        drop.refresh_from_db()
        self.assertEqual(keep.price_delta, Decimal("2.00"))
        self.assertFalse(drop.active)  # retired, never deleted
        self.assertTrue(ProductVariant.objects.filter(pk=drop.pk).exists())

    def test_archived_products_are_hidden_by_default(self):
        Product.objects.create(name="Old", sales_price=Decimal("1.00"),
                               cost_price=Decimal("0.00"), active=False)
        response = self.client.get("/api/products/")
        self.assertEqual(response.json()["count"], 0)
        response = self.client.get("/api/products/", {"include_archived": "true"})
        self.assertEqual(response.json()["count"], 1)

    def test_search_filters_by_name(self):
        self.make_product(name="Alpha")
        self.make_product(name="Beta")
        response = self.client.get("/api/products/", {"q": "alph"})
        self.assertEqual(response.json()["count"], 1)


class PlanApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.auth(self.admin)
        self.product = self.make_product()

    def payload(self, **overrides):
        data = {
            "product": self.product.id, "name": "Monthly", "billing_frequency": "monthly",
            "price": "100.00", "minimum_quantity": 1,
            "availability_start": "2025-01-01",
        }
        data.update(overrides)
        return data

    def test_create_plan(self):
        response = self.client.post("/api/plans/", self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["is_selectable"])

    def test_availability_end_before_start_is_refused(self):
        response = self.client.post(
            "/api/plans/", self.payload(availability_end="2024-01-01")
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("availability_end", response.json()["errors"])

    def test_selectable_filter_excludes_closed_windows(self):
        Plan.objects.create(
            product=self.product, name="Old", billing_frequency="monthly",
            price=Decimal("10.00"), minimum_quantity=1,
            availability_start=date(2020, 1, 1), availability_end=date(2021, 1, 1),
        )
        Plan.objects.create(
            product=self.product, name="Live", billing_frequency="monthly",
            price=Decimal("10.00"), minimum_quantity=1,
            availability_start=date(2020, 1, 1),
        )
        response = self.client.get("/api/plans/", {"selectable": "true"})
        names = [row["name"] for row in response.json()["results"]]
        self.assertEqual(names, ["Live"])

    def test_frequency_filter(self):
        Plan.objects.create(
            product=self.product, name="Yearly", billing_frequency="yearly",
            price=Decimal("1000.00"), minimum_quantity=1,
            availability_start=date(2020, 1, 1),
        )
        self.client.post("/api/plans/", self.payload())
        response = self.client.get("/api/plans/", {"frequency": "yearly"})
        self.assertEqual(
            [row["name"] for row in response.json()["results"]], ["Yearly"]
        )


class TaxRuleApiTests(ApiTestCase):
    def test_rate_above_one_hundred_is_refused(self):
        self.auth(self.admin)
        response = self.client.post("/api/tax-rules/", {"name": "Broken", "rate": "150.00"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("rate", response.json()["errors"])

    def test_valid_rate_is_accepted(self):
        self.auth(self.admin)
        response = self.client.post("/api/tax-rules/", {"name": "VAT", "rate": "5.50"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["rate"], "5.500")


class CustomerApiTests(ApiTestCase):
    def test_staff_create_and_update(self):
        self.auth(self.staff)
        created = self.client.post("/api/customers/", {
            "name": "Rohan Ltd", "city": "Edoras", "contact_email": "ops@rohan.io",
        }).json()
        response = self.client.patch(
            f"/api/customers/{created['id']}/", {"city": "Aldburg"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["city"], "Aldburg")

    def test_blank_name_is_refused(self):
        self.auth(self.staff)
        response = self.client.post("/api/customers/", {"name": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json()["errors"])

    def test_search_and_subscription_count(self):
        self.auth(self.staff)
        self.customer  # shire, has no subscriptions
        response = self.client.get("/api/customers/", {"q": "shire"})
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["subscription_count"], 0)

    def test_pagination_is_bounded(self):
        for i in range(25):
            self.customer.__class__.objects.create(name=f"Co {i:02d}")
        self.auth(self.staff)
        body = self.client.get("/api/customers/", {"page_size": 5}).json()
        self.assertEqual(len(body["results"]), 5)
        self.assertEqual(body["count"], 27)
        capped = self.client.get("/api/customers/", {"page_size": 9999}).json()
        self.assertLessEqual(len(capped["results"]), 200)
