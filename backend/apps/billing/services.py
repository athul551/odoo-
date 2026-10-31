"""
Billing-day machinery (ADR 0001 / ADR 0002 live here).

run_billing_day(on): idempotent, isolated batch.
  - candidates are ACTIVE subscriptions whose term has started, *including*
    terms that have since ended: a period that fell due inside the term is
    billed even if billing day was missed past the expiry (never skipped)
  - every period is anchored on the subscription start and must begin
    on/before `on` and before the expiry
  - a period overlapping a recorded pause is dropped, never deferred
  - an existing non-cancelled invoice for a period means "already billed"
  - a cancelled invoice frees its period -> it gets billed again (ADR 0002)
  - each subscription commits in its own savepoint: one bad record is
    reported in run.report["failed"] and the rest of the batch survives
  - concurrent runs use select_for_update(skip_locked=True): the batches are
    disjoint, and the partial unique index is the final arbiter.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

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


def _candidate_subscriptions(on: date):
    """
    Active terms that had started by `on` — including terms that have already
    ended. Filtering on ``expiry_date__gt=on`` (the old behaviour) silently
    dropped every period that fell due before an unbilled term ran out, which
    is revenue the company can never recover. The per-period bound
    ``cursor < expiry_date`` keeps the scan inside the term.
    """
    return (
        Subscription.objects
        .filter(stage=Stage.ACTIVE, start_date__lte=on)
        .select_related("plan", "customer")
        .order_by("pk")
    )


def _period_starts_due(sub: Subscription, on: date, pauses=()) -> list[date]:
    """
    Every billable period start of this subscription that fell on/before `on`
    and inside the term, minus any period overlapping a recorded pause.

    Idempotency does not live here — the partial unique index
    (invoice_one_per_subscription_period) plus the exists() pre-check in
    run_billing_day make re-scanning from the term start safe even if a
    previous run died mid-batch.
    """
    starts, cursor = [], sub.start_date
    while cursor <= on and cursor < sub.expiry_date:
        period_end = advance(cursor, sub.plan.billing_frequency)
        if period_end <= cursor:  # defensive: arithmetic must always move forward
            break
        paused = any(span.overlaps(cursor, period_end) for span in pauses)
        if not paused:
            starts.append(cursor)
        cursor = period_end
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


def run_billing_day(*, on: date | None = None, actor=None) -> BillingRun:
    """
    Bill everything due on `on`.

    The run row is written *before* any work and outside the batch
    transaction, so an attempt always leaves an audit record even if the
    process dies. Each subscription then commits in its own savepoint: a
    single malformed record is reported in ``report["failed"]`` instead of
    discarding the invoices already built for the other 286 tenants.
    """
    if actor is not None:
        _require_staff(actor)
    on = on or date.today()
    run = BillingRun.objects.create(ran_on=on)

    billed = skipped = locked = failed = 0
    details = {
        "billed": [],
        "skipped_already_billed": [],
        "skipped_locked": [],
        "failed": [],
    }

    candidates = list(_candidate_subscriptions(on).values_list("pk", "number"))
    for pk, number in candidates:
        try:
            with transaction.atomic():
                sub = (
                    Subscription.objects
                    .select_for_update(of=("self",), skip_locked=True)
                    .select_related("plan", "customer")
                    .filter(pk=pk)
                    .first()
                )
                if sub is None:
                    # Another run holds the row: its batch owns this term.
                    locked += 1
                    details["skipped_locked"].append(number)
                    continue

                pauses = list(sub.pause_periods.all())
                # One query per subscription instead of one per period: an old
                # daily term scans hundreds of periods on every run.
                billed_periods = set(
                    sub.invoices.filter(status__in=Invoice.OPEN_STATUSES)
                    .values_list("period_start", flat=True)
                )
                for period_start in _period_starts_due(sub, on, pauses):
                    if period_start in billed_periods:
                        skipped += 1
                        details["skipped_already_billed"].append(
                            [number, period_start.isoformat()]
                        )
                        continue
                    period_end = advance(period_start, sub.plan.billing_frequency)
                    _build_invoice(sub, period_start, period_end, run, on)
                    billed += 1
                    details["billed"].append([number, period_start.isoformat()])
        except Exception as exc:  # one bad record must not sink the batch
            failed += 1
            details["failed"].append(
                {"subscription": number, "error": f"{type(exc).__name__}: {exc}"}
            )

    run.billed_count = billed
    run.skipped_count = skipped
    run.failed_count = failed
    run.report = details
    run.finished_at = timezone.now()
    run.save(update_fields=[
        "billed_count", "skipped_count", "failed_count", "report", "finished_at",
    ])
    return run


def preview_billing_day(*, on: date | None = None, limit: int = 200) -> dict:
    """
    Read-only twin of run_billing_day: the same due-period scan, no writes and
    no row locks. ``missed_periods`` counts periods belonging to a term that
    has already ended — the operator's signal that a billing day was skipped
    and revenue is waiting. ``problems`` lists records the run would fail on.
    """
    on = on or date.today()
    items, problems = [], []
    subscriptions_touched = missed = 0
    for sub in _candidate_subscriptions(on):
        try:
            due_periods = _period_starts_due(sub, on, list(sub.pause_periods.all()))
        except Exception as exc:
            problems.append({"subscription": sub.number,
                             "error": f"{type(exc).__name__}: {exc}"})
            continue
        billed_periods = set(
            sub.invoices.filter(status__in=Invoice.OPEN_STATUSES)
            .values_list("period_start", flat=True)
        )
        pending = [
            start for start in due_periods
            if start not in billed_periods
        ]
        if not pending:
            continue
        subscriptions_touched += 1
        term_ended = sub.expiry_date <= on
        if term_ended:
            missed += len(pending)
        for start in pending:
            items.append({
                "subscription": sub.number,
                "customer": sub.customer.name,
                "period_start": start.isoformat(),
                "period_end": advance(start, sub.plan.billing_frequency).isoformat(),
                "estimated_subtotal": str(sub.subtotal),
                "term_ended": term_ended,
            })
    return {
        "on": on.isoformat(),
        "subscriptions": subscriptions_touched,
        "invoices": len(items),
        "missed_periods": missed,
        "problems": problems,
        "truncated": len(items) > limit,
        "items": items[:limit],
    }


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
    _email_invoice(locked)
    return _sync_back(invoice, locked)


def _email_invoice(invoice: Invoice) -> None:
    """
    Deliver the invoice to the customer's billing contact.

    A customer without a contact email still gets the invoice marked sent (the
    ledger is the truth); the delivery step simply has nowhere to go. Email is
    sent through Django's configured backend, so tests capture it in locmem and
    a deployment needs SMTP configured.
    """
    recipient = (invoice.customer.contact_email or "").strip()
    if not recipient:
        return
    due = invoice.due_date.isoformat() if invoice.due_date else "on receipt"
    send_mail(
        subject=f"Invoice {invoice.number} from Brightloop",
        message=(
            f"Hello {invoice.customer.name},\n\n"
            f"Invoice {invoice.number} covers {invoice.period_start} to "
            f"{invoice.period_end}.\n"
            f"Total: {invoice.total} — amount due: {invoice.amount_due}.\n"
            f"Due date: {due}.\n\n"
            "You can see this invoice and its payment status in the Brightloop portal.\n\n"
            "Thank you,\nBrightloop"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=False,
    )


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
