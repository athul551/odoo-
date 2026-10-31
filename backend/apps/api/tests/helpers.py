from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.billing.models import TaxRule
from apps.customers.models import Customer
from apps.products.models import Plan, Product

User = get_user_model()
PASSWORD = "Sunshine!9qZ"  # 10 chars, upper, lower, special


def make_user(email, role, *, customer=None, password=PASSWORD, **extra):
    return User.objects.create_user(
        email=email, password=password, role=role, customer=customer, **extra
    )


class ApiTestCase(TestCase):
    """Shared cast: one admin, one staff, two customers with portal users."""

    def setUp(self):
        cache.clear()  # throttling state must not leak between tests
        self.admin = make_user("admin@brightloop.io", User.Role.ADMIN)
        self.staff = make_user("staff@brightloop.io", User.Role.STAFF)
        self.customer = Customer.objects.create(name="Shire Logistics")
        self.customer_user = make_user(
            "portal@shire.io", User.Role.CUSTOMER, customer=self.customer
        )
        self.other_customer = Customer.objects.create(name="Mordor Freight")
        self.other_portal = make_user(
            "portal@mordor.io", User.Role.CUSTOMER, customer=self.other_customer
        )
        self.client = APIClient()

    def auth(self, user=None):
        self.client.force_authenticate(user=user or self.staff)
        return self.client

    def anonymous(self):
        self.client.force_authenticate(user=None)
        return self.client

    # -- factories -----------------------------------------------------
    def make_product(self, name="Ops Suite", price="100.00"):
        return Product.objects.create(
            name=name, sales_price=Decimal(price), cost_price=Decimal("10.00")
        )

    def make_plan(self, *, product=None, name="Monthly", frequency="monthly",
             start=date(2025, 1, 1), end=None, minimum=1, price="100.00"):
        return Plan.objects.create(
            product=product or self.make_product(), name=name,
            billing_frequency=frequency, price=Decimal(price),
            minimum_quantity=minimum, availability_start=start, availability_end=end,
        )

    def make_tax(self, rate="18.00", name="GST"):
        return TaxRule.objects.create(name=name, rate=Decimal(rate))
