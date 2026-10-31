from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.accounts.models import User
from apps.billing.models import TaxRule
from apps.common.timeutils import Frequency
from apps.customers.models import Customer
from apps.products.models import Plan, Product, ProductVariant
from apps.quotations.models import QuotationTemplate, QuotationTemplateLine
from apps.subscriptions import services
from apps.subscriptions.models import InvalidTransition, Subscription, SubscriptionLine


def make_user(email, role, **kw):
    return User.objects.create_user(email, "Sunshine!9qZ", role=role, **kw)


class Fixture:
    def __init__(self):
        self.staff = make_user("rep@brightloop.io", User.Role.STAFF)
        self.admin = make_user("boss@brightloop.io", User.Role.ADMIN)
        self.customer_org = Customer.objects.create(name="Acme Ltd")
        self.portal_user = make_user(
            "buyer@acme.io", User.Role.CUSTOMER, customer=self.customer_org
        )
        self.product = Product.objects.create(
            name="Cloud Suite", type=Product.Type.SERVICE,
            sales_price=Decimal("100.00"), cost_price=Decimal("40.00"),
        )
        self.odoo_variant = ProductVariant.objects.create(
            product=self.product, attribute="brand", value="Odoo",
            price_delta=Decimal("560.00"),
        )
        self.tax = TaxRule.objects.create(name="GST", rate=Decimal("18.00"))
        self.plan = Plan.objects.create(
            product=self.product, name="Standard Monthly",
            billing_frequency=Frequency.MONTHLY, price=Decimal("100.00"),
            minimum_quantity=1, availability_start=date(2026, 1, 1),
            auto_close_on_expiry=False, allow_early_close=True,
            allow_pause=True, allow_renew=True,
        )

    def subscription(self, stage=Subscription.Stage.DRAFT, **overrides):
        kw = dict(
            customer=self.customer_org, plan=self.plan, start_date=date(2026, 2, 1),
            actor=self.staff,
        )
        kw.update(overrides)
        sub = services.create_subscription(**kw)
        if stage == Subscription.Stage.DRAFT:
            return sub
        services.add_line(sub=sub, product=self.product, actor=self.staff)
        services.send_quotation(sub=sub, actor=self.staff)
        if stage == Subscription.Stage.QUOTATION:
            return sub
        services.confirm(sub=sub, actor=self.staff)
        if stage == Subscription.Stage.CONFIRMED:
            return sub
        services.activate(sub=sub, actor=self.staff)
        if stage == Subscription.Stage.ACTIVE:
            return sub
        services.close(sub=sub, actor=self.staff)
        return sub


class StageMachineTests(TestCase):
    def setUp(self):
        self.fx = Fixture()

    def test_happy_path_walks_the_full_ladder(self):
        sub = self.fx.subscription()
        self.assertEqual(sub.stage, Subscription.Stage.DRAFT)
        services.add_line(sub=sub, product=self.fx.product, actor=self.fx.staff)
        services.send_quotation(sub=sub, actor=self.fx.staff)
        self.assertEqual(sub.stage, Subscription.Stage.QUOTATION)
        services.confirm(sub=sub, actor=self.fx.staff)
        self.assertEqual(sub.stage, Subscription.Stage.CONFIRMED)
        services.activate(sub=sub, actor=self.fx.staff)
        self.assertEqual(sub.stage, Subscription.Stage.ACTIVE)
        services.close(sub=sub, actor=self.fx.staff)
        self.assertEqual(sub.stage, Subscription.Stage.CLOSED)

    def test_no_skipping_stages(self):
        sub = self.fx.subscription()  # draft
        for fn in (services.confirm, services.activate):
            with self.assertRaises(InvalidTransition):
                fn(sub=sub, actor=self.fx.staff)

    def test_never_backward(self):
        sub = self.fx.subscription(Subscription.Stage.ACTIVE)
        services.close(sub=sub, actor=self.fx.staff)
        with self.assertRaises(InvalidTransition):
            services.activate(sub=sub, actor=self.fx.staff)

    def test_transition_table_is_exhaustive_over_stages(self):
        legal = services.LEGAL_TRANSITIONS
        all_stages = [s.value for s in Subscription.Stage]
        for src, targets in legal.items():
            self.assertIn(src, all_stages)
            for t in targets:
                self.assertIn(t, all_stages)
        self.assertEqual(legal[Subscription.Stage.DRAFT],
                         {Subscription.Stage.QUOTATION, Subscription.Stage.CLOSED})
        self.assertEqual(legal[Subscription.Stage.CLOSED], set())

    def test_send_requires_lines(self):
        sub = self.fx.subscription()
        with self.assertRaises(ValidationError):
            services.send_quotation(sub=sub, actor=self.fx.staff)

    def test_confirm_refuses_lapsed_validity(self):
        sub = self.fx.subscription()
        services.add_line(sub=sub, product=self.fx.product, actor=self.fx.staff)
        services.send_quotation(sub=sub, actor=self.fx.staff)
        self.assertIsNotNone(sub.validity_until)
        late = sub.validity_until + timedelta(days=1)
        with self.assertRaises(ValidationError):
            services.confirm(sub=sub, actor=self.fx.staff, on=late)

    def test_activate_rejects_reordered_dates(self):
        sub = self.fx.subscription(Subscription.Stage.CONFIRMED)
        with self.assertRaises(ValidationError):
            services.activate(sub=sub, actor=self.fx.staff, expiry_date=date(2026, 1, 1))

    def test_customer_role_cannot_operate_the_machine(self):
        sub = self.fx.subscription()
        services.add_line(sub=sub, product=self.fx.product, actor=self.fx.staff)
        with self.assertRaises(PermissionDenied):
            services.send_quotation(sub=sub, actor=self.fx.portal_user)


class NumberingTests(TestCase):
    def setUp(self):
        self.fx = Fixture()

    def test_numbers_are_sequential_and_unique(self):
        subs = []
        for _ in range(3):
            sub = self.fx.subscription()
            subs.append(sub)
        numbers = [s.number for s in subs]
        self.assertEqual(len(set(numbers)), 3)
        year = date.today().year
        self.assertTrue(numbers[0].startswith(f"SUB-{year}-"))
        tails = [int(n.split("-")[-1]) for n in numbers]
        self.assertEqual(tails, sorted(tails))

    def test_number_assigned_at_creation_and_immutable(self):
        sub = self.fx.subscription()
        self.assertTrue(sub.number)
        old = sub.number
        services.add_line(sub=sub, product=self.fx.product, actor=self.fx.staff)
        services.send_quotation(sub=sub, actor=self.fx.staff)
        self.assertEqual(sub.number, old)


class NumberingConcurrencyTests(TransactionTestCase):
    """8 threads race to create subscriptions; numbers must not collide."""

    def setUp(self):
        self.staff = User.objects.create_user("race@x.io", "Sunshine!9qZ", role=User.Role.STAFF)
        self.customer_org = Customer.objects.create(name="Racer Ltd")
        product = Product.objects.create(name="P", sales_price=Decimal("10.00"),
                                         cost_price=Decimal("1.00"))
        self.plan = Plan.objects.create(
            product=product, name="RacePlan", billing_frequency=Frequency.MONTHLY,
            price=Decimal("10.00"), minimum_quantity=1, availability_start=date(2026, 1, 1),
        )

    def test_parallel_numbers_are_unique(self):
        import threading

        results, errors = [], []
        barrier = threading.Barrier(8)

        def make_one():
            try:
                barrier.wait()  # maximise contention
                sub = services.create_subscription(
                    customer=self.customer_org, plan=self.plan,
                    start_date=date(2026, 3, 1), actor=self.staff,
                )
                results.append(sub.number)
            except Exception as e:  # noqa: BLE001
                errors.append(e)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=make_one) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [], f"creation errors: {errors}")
        self.assertEqual(len(results), 8)
        self.assertEqual(len(set(results)), 8, f"collision: {sorted(results)}")


class BehaviorFlagTests(TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.sub = self.fx.subscription(Subscription.Stage.ACTIVE)  # already has one line

    def drive_to_active(self, plan, **kw):
        sub = services.create_subscription(
            customer=self.fx.customer_org, plan=plan, start_date=date(2026, 2, 1),
            expiry_date=kw.pop("expiry_date", None) or date(2027, 2, 1),
            actor=self.fx.staff, **kw,
        )
        services.add_line(sub=sub, product=self.fx.product, actor=self.fx.staff)
        services.send_quotation(sub=sub, actor=self.fx.staff)
        services.confirm(sub=sub, actor=self.fx.staff)
        services.activate(sub=sub, actor=self.fx.staff)
        return sub

    def test_early_close_respects_allow_early_close(self):
        strict_plan = Plan.objects.create(
            product=self.fx.product, name="Locked", billing_frequency=Frequency.MONTHLY,
            price=Decimal("100.00"), minimum_quantity=1, availability_start=date(2026, 1, 1),
            allow_early_close=False,
        )
        sub = self.drive_to_active(strict_plan, expiry_date=date(2027, 1, 1))
        with self.assertRaises(InvalidTransition):
            services.close(sub=sub, actor=self.fx.staff, on=date(2026, 6, 1))
        services.close(sub=sub, actor=self.fx.staff, on=date(2027, 2, 1))  # at expiry: fine
        self.assertEqual(sub.stage, Subscription.Stage.CLOSED)

    def test_pause_flag_respects_allow_pause(self):
        services.set_paused(sub=self.sub, actor=self.fx.staff, paused=True)
        self.assertTrue(self.sub.is_paused)
        services.set_paused(sub=self.sub, actor=self.fx.staff, paused=False)
        self.assertFalse(self.sub.is_paused)

        strict_plan = Plan.objects.create(
            product=self.fx.product, name="NoPause", billing_frequency=Frequency.MONTHLY,
            price=Decimal("50.00"), minimum_quantity=1, availability_start=date(2026, 1, 1),
            allow_pause=False,
        )
        sub = self.drive_to_active(strict_plan, expiry_date=date(2027, 1, 1))
        with self.assertRaises(InvalidTransition):
            services.set_paused(sub=sub, actor=self.fx.staff, paused=True)

    def test_pause_only_on_active(self):
        draft = self.fx.subscription()
        services.add_line(sub=draft, product=self.fx.product, actor=self.fx.staff)
        with self.assertRaises(InvalidTransition):
            services.set_paused(sub=draft, actor=self.fx.staff, paused=True)

    def test_renew_extends_active_by_one_period(self):
        # sub from fixture: monthly, start 2026-02-01, expiry = next_period_start = 2026-03-01
        self.assertEqual(self.sub.expiry_date, date(2026, 3, 1))
        services.renew(sub=self.sub, actor=self.fx.staff, on=date(2026, 2, 20))
        self.assertEqual(self.sub.expiry_date, date(2026, 4, 1))

    def test_renew_requires_allow_renew(self):
        strict_plan = Plan.objects.create(
            product=self.fx.product, name="NoRenew", billing_frequency=Frequency.MONTHLY,
            price=Decimal("50.00"), minimum_quantity=1, availability_start=date(2026, 1, 1),
            allow_renew=False,
        )
        sub = self.drive_to_active(strict_plan, expiry_date=date(2027, 1, 1))
        with self.assertRaises(InvalidTransition):
            services.renew(sub=sub, actor=self.fx.staff)

    def test_renew_after_expiry_reopens_closed(self):
        services.close(sub=self.sub, actor=self.fx.staff, on=date(2026, 2, 15), reason="ops")
        services.renew(sub=self.sub, actor=self.fx.staff, on=date(2026, 3, 20))
        self.assertEqual(self.sub.stage, Subscription.Stage.ACTIVE)
        self.assertGreater(self.sub.expiry_date, self.sub.start_date)

    def test_renew_cannot_reopen_early_closed(self):
        services.close(sub=self.sub, actor=self.fx.staff, on=date(2026, 2, 10))
        with self.assertRaises(InvalidTransition):
            services.renew(sub=self.sub, actor=self.fx.staff, on=date(2026, 2, 20))

    def test_auto_close_sweep_closes_only_auto_plans(self):
        auto_plan = Plan.objects.create(
            product=self.fx.product, name="AutoClose", billing_frequency=Frequency.MONTHLY,
            price=Decimal("50.00"), minimum_quantity=1, availability_start=date(2026, 1, 1),
            auto_close_on_expiry=True,
        )
        auto_sub = self.drive_to_active(auto_plan, expiry_date=date(2026, 2, 28))
        manual_sub = self.sub  # fx plan has auto_close False; setUp's sub already has a line
        closed = services.auto_close_expired(on=date(2026, 3, 1))
        self.assertIn(auto_sub, closed)
        auto_sub.refresh_from_db()
        self.assertEqual(auto_sub.stage, Subscription.Stage.CLOSED)
        manual_sub.refresh_from_db()
        self.assertEqual(manual_sub.stage, Subscription.Stage.ACTIVE)


class LineIntegrityTests(TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.sub = self.fx.subscription()

    def test_variant_delta_flows_into_snapshot_price(self):
        line = services.add_line(
            sub=self.sub, product=self.fx.product, variant=self.fx.odoo_variant,
            actor=self.fx.staff,
        )
        self.assertEqual(line.unit_price, Decimal("660.00"))
        self.assertEqual(line.amount, Decimal("660.00"))

    def test_snapshot_does_not_move_with_product(self):
        line = services.add_line(sub=self.sub, product=self.fx.product, actor=self.fx.staff)
        self.fx.product.sales_price = Decimal("150.00")
        self.fx.product.save()
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("100.00"))

    def test_duplicate_product_line_rejected(self):
        services.add_line(sub=self.sub, product=self.fx.product, actor=self.fx.staff)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SubscriptionLine.objects.create(
                    subscription=self.sub, product=self.fx.product,
                    quantity=2, unit_price=Decimal("99.00"),
                )

    def test_same_product_different_variants_allowed(self):
        extra = ProductVariant.objects.create(product=self.fx.product, attribute="brand",
                                              value="SAP", price_delta=Decimal("50.00"))
        services.add_line(sub=self.sub, product=self.fx.product, variant=self.fx.odoo_variant,
                          actor=self.fx.staff)
        services.add_line(sub=self.sub, product=self.fx.product, variant=extra,
                          actor=self.fx.staff)
        self.assertEqual(self.sub.lines.count(), 2)

    def test_tax_computes_and_totals_recalculate(self):
        line = services.add_line(sub=self.sub, product=self.fx.product, quantity=3,
                                 tax_rule=self.fx.tax, actor=self.fx.staff)
        self.assertEqual(line.amount, Decimal("300.00"))
        self.assertEqual(line.tax_amount, Decimal("54.00"))
        self.sub.refresh_from_db()
        self.assertEqual((self.sub.subtotal, self.sub.tax_total, self.sub.total),
                         (Decimal("300.00"), Decimal("54.00"), Decimal("354.00")))
        services.remove_line(sub=self.sub, line_id=line.pk, actor=self.fx.staff)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.total, Decimal("0.00"))

    def test_minimum_quantity_from_plan_enforced(self):
        seats_plan = Plan.objects.create(
            product=self.fx.product, name="Seat Minimum 5", billing_frequency=Frequency.MONTHLY,
            price=Decimal("10.00"), minimum_quantity=5, availability_start=date(2026, 1, 1),
        )
        sub = services.create_subscription(
            customer=self.fx.customer_org, plan=seats_plan, start_date=date(2026, 2, 1),
            expiry_date=date(2027, 2, 1), actor=self.fx.staff,
        )
        with self.assertRaises(ValidationError):
            services.add_line(sub=sub, product=self.fx.product, quantity=4, actor=self.fx.staff)

    def test_lines_locked_after_confirm(self):
        sub = self.fx.subscription(Subscription.Stage.CONFIRMED)  # already has a line
        with self.assertRaises(ValidationError):
            services.add_line(sub=sub, product=self.fx.product, variant=self.fx.odoo_variant,
                              actor=self.fx.staff)
        with self.assertRaises(ValidationError):
            services.remove_line(sub=sub, line_id=sub.lines.first().pk, actor=self.fx.staff)

    def test_variant_from_other_product_rejected(self):
        other = Product.objects.create(name="Other", sales_price=Decimal("10.00"),
                                       cost_price=Decimal("1.00"))
        bad_variant = ProductVariant.objects.create(product=other, attribute="x", value="y")
        with self.assertRaises(ValidationError):
            services.add_line(sub=self.sub, product=self.fx.product, variant=bad_variant,
                              actor=self.fx.staff)


class AvailabilitySelectionTests(TestCase):
    def setUp(self):
        self.fx = Fixture()

    def test_closed_window_blocks_new_selection(self):
        expired_plan = Plan.objects.create(
            product=self.fx.product, name="Retired", billing_frequency=Frequency.MONTHLY,
            price=Decimal("50.00"), minimum_quantity=1,
            availability_start=date(2025, 1, 1), availability_end=date(2025, 12, 31),
        )
        with self.assertRaises(ValidationError):
            services.create_subscription(
                customer=self.fx.customer_org, plan=expired_plan,
                start_date=date(2026, 2, 1), actor=self.fx.staff,
            )

    def test_existing_subscription_keeps_billing_after_window_closes(self):
        plan = self.fx.plan
        sub = self.fx.subscription(Subscription.Stage.ACTIVE)  # created while window open
        plan.availability_end = date(2026, 2, 28)  # window shuts after creation
        plan.save()
        self.assertFalse(plan.is_selectable(date(2026, 4, 1)))
        # existing subscription stays operable
        services.set_paused(sub=sub, actor=self.fx.staff, paused=True)
        services.set_paused(sub=sub, actor=self.fx.staff, paused=False)
        self.assertEqual(sub.stage, Subscription.Stage.ACTIVE)


class QuotationTemplateTests(TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.template = QuotationTemplate.objects.create(
            name="Big Company Offer", plan=self.fx.plan, validity_days=10,
        )
        QuotationTemplateLine.objects.create(
            template=self.template, product=self.fx.product,
            variant=self.fx.odoo_variant, quantity=2,
        )

    def test_template_seed_copies_lines_and_snapshot_prices(self):
        sub = services.create_subscription(
            customer=self.fx.customer_org, plan=self.fx.plan,
            start_date=date(2026, 2, 1), actor=self.fx.staff,
            origin_template=self.template,
        )
        line = sub.lines.get()
        self.assertEqual(line.variant, self.fx.odoo_variant)
        self.assertEqual(line.unit_price, Decimal("660.00"))
        self.assertEqual(line.quantity, 2)
        self.sub_refresh(sub)

    def test_send_uses_template_validity_days(self):
        sub = services.create_subscription(
            customer=self.fx.customer_org, plan=self.fx.plan,
            start_date=date(2026, 2, 1), actor=self.fx.staff,
            origin_template=self.template,
        )
        services.send_quotation(sub=sub, actor=self.fx.staff, on=date(2026, 2, 1))
        self.assertEqual(sub.validity_until, date(2026, 2, 11))

    def sub_refresh(self, sub):
        sub.refresh_from_db()
        self.assertEqual(sub.subtotal, Decimal("1320.00"))

    def test_template_variants_cannot_borrow_other_products(self):
        other = Product.objects.create(name="Other", sales_price=Decimal("5.00"),
                                       cost_price=Decimal("1.00"))
        with self.assertRaises(ValidationError):
            QuotationTemplateLine(
                template=self.template, product=other, variant=self.fx.odoo_variant,
                quantity=1,
            ).full_clean()

    def test_validity_days_positive(self):
        with self.assertRaises(ValidationError):
            QuotationTemplate(name="Bad", plan=self.fx.plan, validity_days=0).full_clean()


class SchedulerCommandTests(TestCase):
    """
    `auto_close_expired` used to be unreachable code, so the per-plan
    auto-close switch the admin sets did nothing at all.
    """

    def test_sweep_command_closes_auto_close_terms(self):
        import io

        from django.core.management import call_command

        fx = Fixture()
        auto_plan = Plan.objects.create(
            product=fx.product, name="Auto monthly", billing_frequency=Frequency.MONTHLY,
            price=Decimal("100.00"), minimum_quantity=1,
            availability_start=date(2025, 1, 1), auto_close_on_expiry=True,
        )
        auto_sub = Subscription.objects.create(
            number="SUB-AUTO-1", customer=fx.customer_org, plan=auto_plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1),
        )
        manual_sub = Subscription.objects.create(
            number="SUB-MANUAL-1", customer=fx.customer_org, plan=fx.plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1),
        )

        out = io.StringIO()
        call_command("sweep_subscriptions", "--on", "2026-03-01", stdout=out)

        auto_sub.refresh_from_db()
        manual_sub.refresh_from_db()
        self.assertEqual(auto_sub.stage, Subscription.Stage.CLOSED)
        self.assertEqual(manual_sub.stage, Subscription.Stage.ACTIVE)
        self.assertIn("1", out.getvalue())


class BillDayCommandTests(TestCase):
    def test_dry_run_writes_nothing_and_a_real_run_bills(self):
        import io

        from django.core.management import call_command

        from apps.billing.models import Invoice

        fx = Fixture()
        sub = Subscription.objects.create(
            number="SUB-CMD-1", customer=fx.customer_org, plan=fx.plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), subtotal=Decimal("100.00"),
            tax_total=Decimal("18.00"), total=Decimal("118.00"),
        )
        SubscriptionLine.objects.create(
            subscription=sub, product=fx.product, quantity=1,
            unit_price=Decimal("100.00"), tax_rule=fx.tax,
        )

        call_command("bill_day", "--on", "2026-01-05", "--dry-run", stdout=io.StringIO())
        self.assertEqual(Invoice.objects.count(), 0)

        out = io.StringIO()
        call_command("bill_day", "--on", "2026-01-05", stdout=out)
        self.assertEqual(Invoice.objects.filter(subscription=sub).count(), 1)
        self.assertIn("billed", out.getvalue().lower())

    def test_a_failed_record_exits_non_zero_but_keeps_good_invoices(self):
        import io

        from django.core.management import call_command
        from django.core.management.base import CommandError

        from apps.billing.models import BillingRun, Invoice

        fx = Fixture()
        broken_plan = Plan.objects.create(
            product=fx.product, name="Hourly", billing_frequency="hourly",
            price=Decimal("10.00"), minimum_quantity=1,
            availability_start=date(2025, 1, 1),
        )
        broken = Subscription.objects.create(
            number="SUB-CMD-BROKEN", customer=fx.customer_org, plan=broken_plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), subtotal=Decimal("10.00"),
            tax_total=Decimal("1.80"), total=Decimal("11.80"),
        )
        SubscriptionLine.objects.create(
            subscription=broken, product=fx.product, quantity=1,
            unit_price=Decimal("10.00"),
        )
        good = Subscription.objects.create(
            number="SUB-CMD-GOOD", customer=fx.customer_org, plan=fx.plan,
            stage=Subscription.Stage.ACTIVE, start_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), subtotal=Decimal("100.00"),
            tax_total=Decimal("18.00"), total=Decimal("118.00"),
        )
        SubscriptionLine.objects.create(
            subscription=good, product=fx.product, quantity=1,
            unit_price=Decimal("100.00"), tax_rule=fx.tax,
        )

        with self.assertRaises(CommandError):
            call_command(
                "bill_day", "--on", "2026-01-05",
                stdout=io.StringIO(), stderr=io.StringIO(),
            )

        # The scheduler alert must not cost the healthy tenants their invoices.
        self.assertEqual(Invoice.objects.filter(subscription=good).count(), 1)
        self.assertEqual(Invoice.objects.filter(subscription=broken).count(), 0)
        self.assertEqual(BillingRun.objects.latest("id").failed_count, 1)
