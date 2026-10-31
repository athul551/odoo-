"""
Read-only (plus two guarded writes) inspection of the running database.

This exists so an operator can prove the backend's own promises from the UI:
which migrations are applied, what is actually in the tables, what SQL a click
ran, and what a fresh install would need. Everything here is admin-only and
disabled unless ``OPS_TOOLS_ENABLED`` is on (it defaults to DEBUG).
"""

from __future__ import annotations

from datetime import date
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from apps.billing.models import BillingRun, Invoice, TaxRule
from apps.common.timeutils import add_months
from apps.customers.models import Customer
from apps.payments.models import Payment
from apps.products.models import Plan, Product
from apps.subscriptions.models import Subscription
from apps.subscriptions import services as subscription_services

User = get_user_model()


def database_info() -> dict:
    connection = connections["default"]
    settings_dict = connection.settings_dict
    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0].split(",")[0]
    return {
        "engine": connection.vendor,
        "name": settings_dict.get("NAME"),
        "host": settings_dict.get("HOST") or "local socket",
        "port": settings_dict.get("PORT") or "",
        "version": version,
    }


def migration_state() -> dict:
    """Applied and pending migrations, per app, with timestamps."""
    connection = connections["default"]
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    recorded = {
        f"{row.app}.{row.name}": row.applied
        for row in MigrationRecorder(connection).migration_qs
    }

    apps: dict[str, dict] = {}
    for app, name in loader.disk_migrations:
        key = f"{app}.{name}"
        entry = apps.setdefault(
            app, {"app": app, "applied": [], "pending": [], "latest_applied_at": None}
        )
        if key in recorded:
            applied_at = recorded[key]
            entry["applied"].append(
                {
                    "name": name,
                    "applied_at": applied_at.isoformat() if applied_at else None,
                }
            )
            if applied_at and (
                entry["latest_applied_at"] is None
                or applied_at.isoformat() > entry["latest_applied_at"]
            ):
                entry["latest_applied_at"] = applied_at.isoformat()
        else:
            entry["pending"].append(name)

    rows = sorted(apps.values(), key=lambda row: row["app"])
    for row in rows:
        row["applied"].sort(key=lambda item: item["name"])
        row["pending"].sort()
    return {
        "apps": rows,
        "applied_count": sum(len(row["applied"]) for row in rows),
        "pending_count": sum(len(row["pending"]) for row in rows),
    }


def table_stats() -> list[dict]:
    """Every user table with an exact row count and its on-disk size."""
    connection = connections["default"]
    tables = connection.introspection.table_names()
    rows = []
    with connection.cursor() as cursor:
        for table in sorted(tables):
            cursor.execute(f'SELECT count(*) FROM "{table}"')
            count = cursor.fetchone()[0]
            cursor.execute("SELECT pg_total_relation_size(%s::regclass)", [table])
            size = cursor.fetchone()[0]
            rows.append({"table": table, "rows": count, "bytes": size})
    return rows


def business_counts() -> dict:
    from django.db.models import Count

    return {
        "users": User.objects.count(),
        "customers": Customer.objects.count(),
        "products": Product.objects.count(),
        "plans": Plan.objects.count(),
        "subscriptions": Subscription.objects.count(),
        "subscriptions_by_stage": {
            row["stage"]: row["count"]
            for row in Subscription.objects.values("stage").annotate(count=Count("id"))
        },
        "invoices": Invoice.objects.count(),
        "invoices_by_status": {
            row["status"]: row["count"]
            for row in Invoice.objects.values("status").annotate(count=Count("id"))
        },
        "payments": Payment.objects.count(),
        "billing_runs": BillingRun.objects.count(),
    }


def overview() -> dict:
    state = migration_state()
    return {
        "database": database_info(),
        "counts": business_counts(),
        "migrations": {
            "applied": state["applied_count"],
            "pending": state["pending_count"],
        },
        "ops_enabled": bool(settings.OPS_TOOLS_ENABLED),
        "debug": bool(settings.DEBUG),
    }


def apply_migrations() -> dict:
    """Run ``migrate``. Dev tool: the caller must be an admin, and it is off
    unless ops tools are enabled."""
    out = StringIO()
    call_command("migrate", interactive=False, verbosity=1, stdout=out)
    return {"output": out.getvalue(), "state": migration_state()}


DEMO_CUSTOMERS = ("Demo Acme Ltd", "Demo Globex GmbH")


def seed_demo_data(*, actor) -> dict:
    """
    Create one coherent demo tenant so the billing day has something to bill.

    Idempotent: a second call reuses the catalog/customers and creates nothing
    new once the demo subscriptions exist.
    """
    tax, _ = TaxRule.objects.get_or_create(
        name="Demo GST", defaults={"rate": 18}
    )
    product, _ = Product.objects.get_or_create(
        name="Demo Cloud Suite",
        defaults={"type": Product.Type.SERVICE, "sales_price": 100, "cost_price": 40},
    )
    plan, _ = Plan.objects.get_or_create(
        product=product,
        name="Demo Monthly",
        defaults={
            "billing_frequency": "monthly",
            "price": 100,
            "minimum_quantity": 1,
            "availability_start": date(2025, 1, 1),
            "auto_close_on_expiry": True,
            "allow_early_close": True,
            "allow_pause": True,
            "allow_renew": True,
        },
    )
    customers = [
        Customer.objects.get_or_create(name=name)[0] for name in DEMO_CUSTOMERS
    ]

    created: list[str] = []
    if not Subscription.objects.filter(customer__in=customers).exists():
        today = date.today()
        back = add_months(today.replace(day=1), -6)

        def build(stage: str, customer: Customer, *, start: date, expiry: date):
            sub = subscription_services.create_subscription(
                customer=customer, plan=plan, start_date=start,
                expiry_date=expiry, actor=actor,
            )
            subscription_services.add_line(
                sub=sub, product=product, tax_rule=tax, quantity=1, actor=actor
            )
            subscription_services.send_quotation(sub=sub, actor=actor)
            if stage == Subscription.Stage.QUOTATION:
                return sub
            subscription_services.confirm(sub=sub, actor=actor)
            if stage == Subscription.Stage.CONFIRMED:
                return sub
            subscription_services.activate(
                sub=sub, actor=actor, start_date=start, expiry_date=expiry
            )
            return sub

        unbilled = build(
            Subscription.Stage.ACTIVE, customers[0],
            start=back, expiry=date(back.year + 1, back.month, 1),
        )
        created.append(unbilled.number)

        paused = build(
            Subscription.Stage.ACTIVE, customers[1],
            start=date(today.year, today.month, 1),
            expiry=date(today.year + 1, today.month, 1),
        )
        subscription_services.set_paused(
            sub=paused, actor=actor, paused=True, on=today
        )
        created.append(paused.number)

        draft = subscription_services.create_subscription(
            customer=customers[1], plan=plan,
            start_date=date(today.year, today.month, 1),
            expiry_date=date(today.year + 1, today.month, 1), actor=actor,
        )
        subscription_services.add_line(
            sub=draft, product=product, tax_rule=tax, quantity=1, actor=actor
        )
        created.append(draft.number)

    return {
        "customers": [customer.name for customer in customers],
        "plan": plan.name,
        "product": product.name,
        "subscriptions": created,
        "already_present": not created,
    }
