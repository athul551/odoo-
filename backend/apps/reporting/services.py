"""
Finance-lead reporting: one summary plus the two chase lists (outstanding,
overdue), computed with SQL aggregates over indexed columns — never by
walking thousands of rows in Python.

MRR model: every ACTIVE, unpaused subscription contributes its current
line subtotal normalised to a month. Daily and weekly factors use the
calendar-exact conversions below; the formula is part of the domain and
unit-tested, not an ad-hoc spreadsheet guess.
"""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum

from apps.billing.models import Invoice
from apps.payments.models import Payment
from apps.subscriptions.models import Subscription

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=16, decimal_places=2)

# monthly-normalisation factors, Decimal so the arithmetic is exact
MONTHS_PER_PERIOD = {
    "daily": Decimal("365") / Decimal("12"),      # ~30.4167 days/month
    "weekly": Decimal("52") / Decimal("12"),      # ~4.3333 weeks/month
    "monthly": Decimal("1"),
    "yearly": Decimal("1") / Decimal("12"),
}


def mrr_expression(alias: str = "mrr_share") -> ExpressionWrapper:
    """Annotate a subscription queryset with its monthly-normalised subtotal."""
    from django.db.models import Case, Value, When
    return ExpressionWrapper(
        Case(
            When(plan__billing_frequency="daily",
                 then=F("subtotal") * Value(Decimal("365")) / Value(Decimal("12"))),
            When(plan__billing_frequency="weekly",
                 then=F("subtotal") * Value(Decimal("52")) / Value(Decimal("12"))),
            When(plan__billing_frequency="monthly", then=F("subtotal")),
            When(plan__billing_frequency="yearly",
                 then=F("subtotal") / Value(Decimal("12"))),
            default=Value(ZERO),
            output_field=MONEY,
        ),
        output_field=MONEY,
    )


def _active_subs_qs(*, customer_id=None, on: date | None = None):
    """
    Revenue-bearing terms: Active, not paused, and still inside their term.
    Nothing closes an expired Active automatically for every plan, so without
    the expiry bound yesterday's contracts inflate MRR/ARR forever.
    """
    on = on or date.today()
    qs = Subscription.objects.filter(
        stage=Subscription.Stage.ACTIVE, is_paused=False, expiry_date__gt=on
    ).exclude(subtotal=ZERO)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    return qs


def month_end_defaults(on: date | None = None) -> tuple[date, date]:
    """First/last day of the month containing `on` (month-end view default)."""
    on = on or date.today()
    start = on.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1) - timedelta(days=1)
    return start, end


def summary(*, start: date | None = None, end: date | None = None,
            customer_id=None, on: date | None = None) -> dict:
    """
    The single month-end picture: active subscriptions, recurring revenue,
    invoiced vs collected, still owed, overdue. Window applies to what was
    invoiced (issued_at) and collected (paid_on); counts are as-of `on`.
    """
    on = on or date.today()
    if start is None and end is None:
        start, end = month_end_defaults(on)
    elif start is not None and end is None:
        end = month_end_defaults(start)[1]   # window closes at the end of start's month
    elif end is not None and start is None:
        start = month_end_defaults(end)[0]   # window opens at the start of end's month
    if start > end:
        raise ValidationError({"start": "Window start cannot be after window end."})

    subs = _active_subs_qs(customer_id=customer_id, on=on)
    agg = subs.aggregate(mrr=Sum(mrr_expression()) or ZERO)
    mrr = (agg["mrr"] or ZERO).quantize(Decimal("0.01"))

    counts = subs.values("plan__billing_frequency").annotate(n=Count("pk"))
    by_frequency = {row["plan__billing_frequency"]: row["n"] for row in counts}

    active_count = sum(by_frequency.values())
    paused_count = Subscription.objects.filter(
        stage=Subscription.Stage.ACTIVE, is_paused=True, expiry_date__gt=on,
        **({"customer_id": customer_id} if customer_id else {}),
    ).count()

    inv_window = Q(issued_at__date__gte=start, issued_at__date__lte=end)
    pay_window = Q(paid_on__gte=start, paid_on__lte=end)
    cust_q = Q(customer_id=customer_id) if customer_id else Q()
    # Payments belong to invoices; the customer filter goes through the invoice.
    pay_cust_q = Q(invoice__customer_id=customer_id) if customer_id else Q()

    invoiced = Invoice.objects.filter(inv_window & cust_q & ~Q(status=Invoice.Status.CANCELLED)
                                      ).aggregate(total=Sum("total") or ZERO)
    collected = Payment.objects.filter(
        pay_window & pay_cust_q & ~Q(invoice__status=Invoice.Status.CANCELLED)
    ).aggregate(total=Sum("amount") or ZERO)
    outstanding = Invoice.objects.filter(
        cust_q, status=Invoice.Status.CONFIRMED,
        due_date__gt=on,
    ).aggregate(amount=Sum(
        ExpressionWrapper(F("total") - F("amount_paid"), output_field=MONEY)
    ) or ZERO, count=Count("pk"))
    overdue = Invoice.objects.filter(
        cust_q, status=Invoice.Status.CONFIRMED, due_date__lte=on,
    ).aggregate(amount=Sum(
        ExpressionWrapper(F("total") - F("amount_paid"), output_field=MONEY)
    ) or ZERO, count=Count("pk"))

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "as_of": on.isoformat()},
        "active_subscriptions": active_count,
        "active_by_frequency": by_frequency,
        "paused_subscriptions": paused_count,
        "mrr": str(mrr),
        "arr": str((mrr * 12).quantize(Decimal("0.01"))),
        "invoiced_total": str((invoiced["total"] or ZERO).quantize(Decimal("0.01"))),
        "collected_total": str((collected["total"] or ZERO).quantize(Decimal("0.01"))),
        "outstanding": {"count": outstanding["count"],
                        "amount": str((outstanding["amount"] or ZERO).quantize(Decimal("0.01")))},
        "overdue": {"count": overdue["count"],
                    "amount": str((overdue["amount"] or ZERO).quantize(Decimal("0.01")))},
    }


def chase_qs(*, kind: str, customer_id=None, on: date | None = None,
             older_than_days: int | None = None):
    """
    The two operational lists: outstanding (not yet due) and overdue (past
    due). `older_than_days` narrows the overdue chase to invoices at least N
    days past their due date. Ordered most-overdue-first.
    """
    on = on or date.today()
    if kind == "overdue":
        qs = Invoice.objects.filter(status=Invoice.Status.CONFIRMED, due_date__lte=on)
        if older_than_days is not None:
            qs = qs.filter(due_date__lte=on - timedelta(days=older_than_days))
    elif kind == "outstanding":
        qs = Invoice.objects.filter(status=Invoice.Status.CONFIRMED, due_date__gt=on)
    else:
        raise ValueError(f"unknown chase kind: {kind}")
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    return (
        qs.select_related("customer", "subscription")
        .order_by(F("due_date").asc(nulls_last=True), "-total")
    )
