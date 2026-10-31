"""
Billing-day machinery (ADR 0001 / ADR 0002 live here).

run_billing_day(on): transactional, idempotent batch.
  - ACTIVE, unpaused subscriptions whose term is running are candidates
  - every period anchored on the subscription start, beginning on/before `on`
    and before the expiry, is billed exactly once
  - an existing non-cancelled invoice for a period means "already billed" -> skip
  - a cancelled invoice frees its period -> it gets billed again (credit-then-rebill)
  - concurrent runs use select_for_update(skip_locked=True): the batches are
    disjoint, and the partial unique index is the final arbiter.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.common.models import NumberSeries
from apps.common.timeutils import advance
from apps.subscriptions.models import Subscription

from .models import AppliedDiscount, BillingRun, DiscountRule, Invoice, InvoiceLine

ZERO = Decimal("0.00")
Stage = Subscription.Stage
Status = Invoice.Status


def _require_staff(actor):
    if not getattr(actor, "is_member_of_staff", False):
        raise PermissionDenied("Only admin or staff may operate invoices.")


def _require_admin(actor):
    if not getattr(actor, "is_admin", False):
        raise PermissionDenied("Only an admin may create or change discount rules.")


@transaction.atomic
def create_discount_rule(*, actor, name, kind, value, scope, applies_from,
                         applies_until=None, minimum_amount=None, minimum_quantity=None,
                         usage_limit=None, product_ids=(), subscription_ids=(),
                         active=True) -> DiscountRule:
    _require_admin(actor)
    rule = DiscountRule(
        name=name, kind=kind, value=Decimal(str(value)), scope=scope,
        applies_from=applies_from, applies_until=applies_until,
        minimum_amount=(Decimal(str(minimum_amount)) if minimum_amount is not None else None),
        minimum_quantity=minimum_quantity, usage_limit=usage_limit, active=active,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    rule.full_clean(exclude=["products", "subscriptions"])
    rule.save()
    if product_ids:
        if scope != DiscountRule.Scope.PRODUCT:
            raise ValidationError({"scope": "Products require a product-scoped rule."})
        rule.products.set(list(product_ids))
    if subscription_ids:
        if scope != DiscountRule.Scope.SUBSCRIPTION:
            raise ValidationError({"scope": "Subscriptions require a subscription-scoped rule."})
        rule.subscriptions.set(list(subscription_ids))
    return rule


@transaction.atomic
def deactivate_discount_rule(*, rule: DiscountRule, actor) -> DiscountRule:
    """
    Retires a rule without deleting history: applied discounts on issued
    invoices stay valid (CONTEXT.md: never revoked from invoices already
    issued), but future billing runs won't choose it.
    """
    _require_admin(actor)
    locked = DiscountRule.objects.select_for_update().get(pk=rule.pk)
    locked.active = False
    locked.save(update_fields=["active"])
    rule.__dict__.update({k: v for k, v in locked.__dict__.items() if k != "_state"})
    return rule


def _period_starts_due(sub: Subscription, on: date) -> list[date]:
    """
    Every period of this subscription that started on/before `on` and before
    expiry. Idempotency does not live here — it is guaranteed by the partial
    unique index (invoice_one_per_subscription_period) plus the exists()
    pre-check in run_billing_day, so scanning from the term start is safe
    even if a previous run died mid-batch.
    """
    starts, cursor = [], sub.start_date
    while cursor <= on and cursor < sub.expiry_date:
        starts.append(cursor)
        nxt = advance(cursor, sub.plan.billing_frequency)
        if nxt <= cursor:  # defensive: arithmetic must always move forward
            break
        cursor = nxt
    return starts


def _build_invoice(sub: Subscription, period_start: date, period_end: date,
                   run: BillingRun | None, on: date) -> Invoice:
    number = NumberSeries.next_number("INV", on.year)
    invoice = Invoice.objects.create(
        number=number, subscription=sub, customer=sub.customer, run=run,
        period_start=period_start, period_end=period_end, status=Status.DRAFT,
    )
    subtotal = ZERO
    for line in sub.lines.select_related("tax_rule", "product", "variant"):
        rate = line.tax_rule.rate if line.tax_rule_id else Decimal("0")
        snapshot = InvoiceLine(
            invoice=invoice,
            description=f"{line.product.name}"
                        + (f" — {line.variant.value}" if line.variant_id else ""),
            product=line.product, variant=line.variant,
            quantity=line.quantity, unit_price=line.unit_price, tax_rate=rate,
        )
        snapshot.save()
        subtotal += snapshot.base_amount
    invoice.subtotal = subtotal
    invoice.save(update_fields=["subtotal"])
    _apply_discounts(invoice, on)
    _recompute_totals(invoice)
    return invoice


def _recompute_totals(invoice: Invoice) -> Invoice:
    """Derive discount/tax/total from the line snapshots — lines are the truth."""
    subtotal = sum((l.base_amount for l in invoice.lines.all()), ZERO)
    discount_total = sum((l.discount for l in invoice.lines.all()), ZERO)
    tax_total = sum((l.tax_amount for l in invoice.lines.all()), ZERO)
    invoice.subtotal = subtotal
    invoice.discount_total = discount_total
    invoice.tax_total = tax_total
    invoice.total = subtotal - discount_total + tax_total
    invoice.save(update_fields=["subtotal", "discount_total", "tax_total", "total", "updated_at"])
    return invoice


# ---------------------------------------------------------------------------
# automatic discount selection (CONTEXT.md: One Discount per Line,
# One Order Discount per Invoice; usage is consumed per invoice)
# ---------------------------------------------------------------------------

def _apply_discounts(invoice: Invoice, on: date) -> None:
    """
    Called inside the run's transaction. Rules are row-locked in pk order
    (deterministic, deadlock-free) so two concurrent runs can never both
    consume a rule's final use.
    """
    candidates = list(
        DiscountRule.objects.select_for_update(of=("self",))
        .filter(active=True)
        .order_by("pk")
    )
    candidates = [r for r in candidates if r.is_within_window(on) and r.has_capacity(on)]

    lines = list(invoice.lines.select_related("product"))
    sub = invoice.subscription

    # ---- product-scoped: best eligible rule per line, never stacked
    for line in lines:
        best_rule, best_value = None, ZERO
        for rule in candidates:
            if rule.scope != DiscountRule.Scope.PRODUCT:
                continue
            allowed = set(rule.products.values_list("id", flat=True))
            if allowed and line.product_id not in allowed:
                continue
            if not _minimums_met(rule, base=line.base_amount, quantity=line.quantity):
                continue
            value = rule.value_for(line.base_amount)
            if value > best_value:
                best_rule, best_value = rule, value
        if best_rule is None:
            continue
        if _remaining_capacity(best_rule, on, invoice) <= ZERO:
            continue
        line.discount = best_value
        line.save(update_fields=["discount", "amount", "tax_amount"])
        AppliedDiscount.objects.create(invoice=invoice, rule=best_rule, line=line, amount=best_value)

    # ---- subscription-scoped: one rule, computed after line discounts
    post_line_subtotal = sum((l.amount for l in lines), ZERO)  # base - line discounts
    if post_line_subtotal <= ZERO:
        return
    best_rule, best_value = None, ZERO
    for rule in candidates:
        if rule.scope != DiscountRule.Scope.SUBSCRIPTION:
            continue
        listed = set(rule.subscriptions.values_list("id", flat=True))
        if listed and sub.id not in listed:
            continue
        total_qty = sum(l.quantity for l in lines)
        if not _minimums_met(rule, base=post_line_subtotal, quantity=total_qty):
            continue
        value = rule.value_for(post_line_subtotal)
        if value > best_value:
            best_rule, best_value = rule, value
    if best_rule is None:
        return
    if _remaining_capacity(best_rule, on, invoice) <= ZERO:
        return
    discount = best_value  # value_for already caps at the base

    allocated = _allocate(discount, [l.amount for l in lines])
    for line, share in zip(lines, allocated):
        if share > 0:
            line.discount += share
            line.save(update_fields=["discount", "amount", "tax_amount"])
    AppliedDiscount.objects.create(invoice=invoice, rule=best_rule, line=None, amount=discount)


def _minimums_met(rule: DiscountRule, *, base: Decimal, quantity: int) -> bool:
    if rule.minimum_amount is not None and base < rule.minimum_amount:
        return False
    if rule.minimum_quantity is not None and quantity < rule.minimum_quantity:
        return False
    return True


def _remaining_capacity(rule: DiscountRule, on: date, invoice: Invoice) -> Decimal:
    """
    Ceiling for money this rule may grant on THIS invoice: the subtotal, or
    nothing once its usage limit is spent on other invoices. The current
    invoice never counts against itself (use = invoice, not line).
    """
    if rule.usage_limit is not None:
        used_elsewhere = (
            rule.applications.exclude(invoice__status=Invoice.Status.CANCELLED)
            .exclude(invoice=invoice)
            .values("invoice_id").distinct().count()
        )
        if used_elsewhere >= rule.usage_limit:
            return ZERO
    return invoice.subtotal


def _allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Pro-rata split of `total` across `weights` in whole cents, remainder to the largest."""
    base_sum = sum(weights, ZERO)
    if base_sum <= 0 or not weights:
        return [ZERO] * len(weights)
    parts = [(total * w / base_sum).quantize(Decimal("0.01")) for w in weights]
    drift = (total - sum(parts, ZERO)).quantize(Decimal("0.01"))
    if drift != ZERO:
        idx = max(range(len(weights)), key=lambda i: weights[i])
        parts[idx] += drift
    return parts


@transaction.atomic
def run_billing_day(*, on: date | None = None, actor=None) -> BillingRun:
    if actor is not None:
        _require_staff(actor)
    on = on or date.today()
    run = BillingRun.objects.create(ran_on=on)

    candidates = (
        Subscription.objects.select_for_update(of=("self",), skip_locked=True)
        .filter(stage=Stage.ACTIVE, is_paused=False, expiry_date__gt=on)
        .select_related("plan", "customer")
        .order_by("pk")
    )

    billed, skipped = 0, 0
    details = {"billed": [], "skipped_already_billed": [], "skipped_paused": []}
    for sub in candidates:
        for period_start in _period_starts_due(sub, on):
            exists = sub.invoices.filter(
                period_start=period_start, status__in=Invoice.OPEN_STATUSES
            ).exists()
            if exists:
                skipped += 1
                details["skipped_already_billed"].append((sub.id, str(period_start)))
                continue
            period_end = advance(period_start, sub.plan.billing_frequency)
            _build_invoice(sub, period_start, period_end, run, on)
            billed += 1
            details["billed"].append((sub.id, str(period_start)))

    run.billed_count = billed
    run.skipped_count = skipped
    run.report = details
    run.finished_at = timezone.now()
    run.save(update_fields=["billed_count", "skipped_count", "report", "finished_at"])
    return run


# ---------------------------------------------------------------------------
# invoice lifecycle
# ---------------------------------------------------------------------------

def _sync_back(original: Invoice, locked: Invoice) -> Invoice:
    """
    The locked row is the truth after the write; mirror it onto the caller's
    instance so nobody operates on a stale snapshot after a successful move.
    """
    original.__dict__.update({k: v for k, v in locked.__dict__.items() if k != "_state"})
    original._state.db = locked._state.db
    return original


@transaction.atomic
def confirm_invoice(*, invoice: Invoice, actor) -> Invoice:
    _require_staff(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != Status.DRAFT:
        raise ValidationError(
            {"status": f"Only Draft invoices can be confirmed (now {locked.status})."}
        )
    if not locked.lines.exists():
        raise ValidationError({"lines": "Cannot confirm an invoice without lines."})
    now = timezone.now()
    locked.status = Status.CONFIRMED
    locked.issued_at = now
    locked.due_date = now.date() + timedelta(days=locked.subscription.payment_terms_days)
    locked.save(update_fields=["status", "issued_at", "due_date", "updated_at"])
    return _sync_back(invoice, locked)


@transaction.atomic
def send_invoice(*, invoice: Invoice, actor) -> Invoice:
    """Only confirmed invoices go out; a draft that was never confirmed can't be sent."""
    _require_staff(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != Status.CONFIRMED:
        raise ValidationError({"status": "Only Confirmed invoices can be sent."})
    locked.sent_at = timezone.now()
    locked.save(update_fields=["sent_at", "updated_at"])
    return _sync_back(invoice, locked)


@transaction.atomic
def mark_printed(*, invoice: Invoice, actor) -> Invoice:
    _require_staff(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status == Status.CANCELLED:
        raise ValidationError({"status": "A cancelled invoice must not be printed."})
    locked.printed_at = timezone.now()
    locked.save(update_fields=["printed_at", "updated_at"])
    return _sync_back(invoice, locked)


@transaction.atomic
def cancel_invoice(*, invoice: Invoice, actor, reason: str = "") -> Invoice:
    """
    ADR 0002: cancellation is credit-then-rebill. A confirmed/paid invoice
    cannot be cancelled while payments are attached — remove the payments
    first. Cancelling frees the period for the next billing run.
    """
    _require_staff(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status == Status.CANCELLED:
        raise ValidationError({"status": "Already cancelled."})
    if locked.status != Status.DRAFT and locked.payments.exists():
        raise ValidationError(
            {"payments": "Remove attached payments before cancelling a confirmed/paid invoice."}
        )
    locked.status = Status.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    return _sync_back(invoice, locked)
