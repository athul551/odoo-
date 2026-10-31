from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.common.timeutils import Frequency, add_months, advance, period_bounds
from apps.products.models import Plan, Product, ProductVariant


def make_product(**kw):
    kw.setdefault("name", "Cloud Suite")
    kw.setdefault("sales_price", Decimal("100.00"))
    kw.setdefault("cost_price", Decimal("40.00"))
    return Product.objects.create(**kw)


def make_plan(product=None, **kw):
    kw.setdefault("name", "Standard Monthly")
    kw.setdefault("billing_frequency", Frequency.MONTHLY)
    kw.setdefault("price", Decimal("100.00"))
    kw.setdefault("availability_start", date(2026, 1, 1))
    return Plan.objects.create(product=product or make_product(), **kw)


class PeriodArithmeticTests(TestCase):
    def test_month_end_clamps_then_recovers(self):
        self.assertEqual(advance(date(2026, 1, 31), Frequency.MONTHLY), date(2026, 2, 28))
        # anchored on Feb 28 (clamped), the next month returns to the 31st: no drift
        self.assertEqual(advance(date(2026, 2, 28), Frequency.MONTHLY), date(2026, 3, 28))
        # leap year
        self.assertEqual(advance(date(2024, 1, 31), Frequency.MONTHLY), date(2024, 2, 29))

    def test_yearly_leap_day_anchor_clamps(self):
        self.assertEqual(advance(date(2024, 2, 29), Frequency.YEARLY), date(2025, 2, 28))
        self.assertEqual(advance(date(2024, 2, 29), Frequency.YEARLY, 4), date(2028, 2, 29))

    def test_daily_weekly(self):
        self.assertEqual(advance(date(2026, 3, 5), Frequency.DAILY), date(2026, 3, 6))
        self.assertEqual(advance(date(2026, 3, 5), Frequency.WEEKLY, 2), date(2026, 3, 19))

    def test_bounds_are_half_open(self):
        start, end = period_bounds(date(2026, 1, 1), Frequency.MONTHLY)
        self.assertEqual((start, end), (date(2026, 1, 1), date(2026, 2, 1)))

    def test_rejects_negative_periods_and_unknown_frequency(self):
        with self.assertRaises(ValueError):
            advance(date(2026, 1, 1), Frequency.MONTHLY, -1)
        with self.assertRaises(ValueError):
            advance(date(2026, 1, 1), "fortnightly")

    def test_add_months_across_year_boundary(self):
        self.assertEqual(add_months(date(2026, 11, 30), 2), date(2027, 1, 30))
        self.assertEqual(add_months(date(2026, 1, 1), -1), date(2025, 12, 1))


class VariantTests(TestCase):
    def test_effective_price_adds_delta(self):
        product = make_product(sales_price=Decimal("1000.00"))
        variant = ProductVariant.objects.create(
            product=product, attribute="brand", value="Odoo", price_delta=Decimal("560.00")
        )
        self.assertEqual(variant.effective_price, Decimal("1560.00"))

    def test_negative_effective_price_rejected(self):
        product = make_product(sales_price=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            ProductVariant(
                product=product, attribute="brand", value="Cheap",
                price_delta=Decimal("-150.00"),
            ).full_clean()

    def test_variant_axis_value_unique(self):
        product = make_product()
        ProductVariant.objects.create(product=product, attribute="brand", value="Odoo")
        try:
            with transaction.atomic():
                ProductVariant.objects.bulk_create([
                    ProductVariant(product=product, attribute="brand", value="Odoo",
                                   price_delta=Decimal("5.00")),
                ])
            self.fail("Expected IntegrityError")
        except IntegrityError:
            pass
        # different attribute, same value is allowed
        ProductVariant.objects.create(product=product, attribute="region", value="Odoo")

    def test_variant_survives_product_price_change(self):
        """Delta semantics: re-pricing the product flows through to variants."""
        product = make_product(sales_price=Decimal("100.00"))
        variant = ProductVariant.objects.create(product=product, attribute="brand", value="Odoo",
                                                price_delta=Decimal("560.00"))
        product.sales_price = Decimal("200.00")
        product.save()
        variant.refresh_from_db()
        self.assertEqual(variant.effective_price, Decimal("760.00"))


class PlanTests(TestCase):
    def test_availability_window_governs_selection_only(self):
        plan = make_plan(availability_start=date(2026, 1, 1), availability_end=date(2026, 3, 31))
        self.assertFalse(plan.is_selectable(date(2025, 12, 31)))
        self.assertTrue(plan.is_selectable(date(2026, 1, 1)))
        self.assertTrue(plan.is_selectable(date(2026, 3, 31)))
        self.assertFalse(plan.is_selectable(date(2026, 4, 1)))
        # open-ended window
        forever = make_plan(name="Forever", availability_start=date(2026, 1, 1))
        self.assertTrue(forever.is_selectable(date(2099, 1, 1)))

    def test_inactive_plan_not_selectable(self):
        plan = make_plan(active=False)
        self.assertFalse(plan.is_selectable(date.today()))

    def test_inverted_window_rejected_at_app_and_db_layers(self):
        product = make_product()
        bad = Plan(product=product, name="Bad", billing_frequency=Frequency.MONTHLY,
                   price=Decimal("10.00"), minimum_quantity=1,
                   availability_start=date(2026, 5, 1), availability_end=date(2026, 4, 1))
        with self.assertRaises(ValidationError):
            bad.full_clean()
        bad = Plan(product=product, name="Bad2", billing_frequency=Frequency.MONTHLY,
                   price=Decimal("10.00"), minimum_quantity=1,
                   availability_start=date(2026, 5, 1), availability_end=date(2026, 4, 1))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                bad.save()

    def test_minimum_quantity_must_be_positive(self):
        product = make_product()
        with self.assertRaises(ValidationError):
            Plan(product=product, name="Bad", billing_frequency=Frequency.MONTHLY,
                 price=Decimal("10.00"), minimum_quantity=0,
                 availability_start=date(2026, 1, 1)).full_clean()
        bad = Plan(product=product, name="Bad2", billing_frequency=Frequency.MONTHLY,
                   price=Decimal("10.00"), minimum_quantity=0,
                   availability_start=date(2026, 1, 1))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                bad.save()

    def test_negative_price_rejected(self):
        product = make_product()
        with self.assertRaises(ValidationError):
            Plan(product=product, name="Bad", billing_frequency=Frequency.MONTHLY,
                 price=Decimal("-1.00"), minimum_quantity=1,
                 availability_start=date(2026, 1, 1)).full_clean()
        bad = Plan(product=product, name="Bad2", billing_frequency=Frequency.MONTHLY,
                   price=Decimal("-1.00"), minimum_quantity=1,
                   availability_start=date(2026, 1, 1))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                bad.save()

    def test_plan_name_unique_per_product(self):
        product = make_product()
        make_plan(product=product, name="Pro")
        try:
            with transaction.atomic():
                Plan.objects.bulk_create([
                    Plan(product=product, name="Pro", billing_frequency=Frequency.MONTHLY,
                         price=Decimal("10.00"), availability_start=date(2026, 1, 1)),
                ])
            self.fail("Expected IntegrityError")
        except IntegrityError:
            pass
        # another product may reuse the name
        make_plan(product=make_product(name="Other"), name="Pro")

    def test_plan_cannot_delete_product_with_plans(self):
        product = make_product()
        make_plan(product=product)
        with self.assertRaises(ProtectedError):
            product.delete()

    def test_next_period_start_uses_plan_frequency(self):
        plan = make_plan(billing_frequency=Frequency.MONTHLY)
        self.assertEqual(plan.next_period_start(date(2026, 1, 31)), date(2026, 2, 28))
