"""
All subscription state moves funnel through this module. Models stay declarative;
services enforce the CONTEXT.md rules: who may act, plan Behaviors, validity,
line integrity, and the linear stage machine.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.common.models import NumberSeries
from apps.common.timeutils import advance

from .models import InvalidTransition, PausePeriod, Subscription, SubscriptionLine

Stage = Subscription.Stage

LEGAL_TRANSITIONS = {
    Stage.DRAFT: {Stage.QUOTATION, Stage.CLOSED},
    Stage.QUOTATION: {Stage.CONFIRMED, Stage.CLOSED},
    Stage.CONFIRMED: {Stage.ACTIVE, Stage.CLOSED},
    Stage.ACTIVE: {Stage.CLOSED},
    Stage.CLOSED: set(),  # renew() re-opens via explicit service, never a stage loop
}


def _require_staff(actor):
    if not getattr(actor, "is_member_of_staff", False):
        raise PermissionDenied("Only admin or staff may operate subscriptions.")


def _check_transition(sub: Subscription, target: str) -> None:
    if target not in LEGAL_TRANSITIONS[sub.stage]:
        raise InvalidTransition(sub, target, "stage sequence is linear and never backward")


def _sync_back(original: Subscription, locked: Subscription) -> Subscription:
    """Mirror a row we re-read under lock onto the caller's instance."""
    original.__dict__.update({k: v for k, v in locked.__dict__.items() if k != "_state"})
    original._state.db = locked._state.db
    return original


def _close_open_pause(sub: Subscription, on: date) -> None:
    """End any pause span still open, so it cannot swallow future periods."""
    for span in sub.pause_periods.filter(ended_on__isnull=True):
        span.ended_on = max(on, span.started_on)
        span.save(update_fields=["ended_on"])


def _transition(sub: Subscription, target: str, *, reason: str = "") -> None:
    _check_transition(sub, target)
    sub.stage = target
    sub.save(update_fields=["stage", "updated_at"])


# ---------------------------------------------------------------------------
# creation
# ---------------------------------------------------------------------------

@transaction.atomic
def create_subscription(
    *, customer, plan, start_date: date, expiry_date: date | None = None,
    payment_terms_days: int = 30, actor, origin_template=None,
) -> Subscription:
    """New Draft subscription with a gap-free number. Plan must be selectable today."""
    _require_staff(actor)
    on = date.today()
    if not plan.is_selectable(on):
        raise ValidationError({"plan": "Plan is not selectable for new subscriptions today."})
    expiry = expiry_date or plan.next_period_start(start_date)
    if expiry <= start_date:
        raise ValidationError({"expiry_date": "Expiry must be after the start date."})

    number = NumberSeries.next_number("SUB", on.year)
    sub = Subscription.objects.create(
        number=number, customer=customer, plan=plan, stage=Stage.DRAFT,
        start_date=start_date, expiry_date=expiry,
        payment_terms_days=payment_terms_days, origin_template=origin_template,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    if origin_template is not None:
        _copy_template_lines(sub, origin_template)
    return sub


def _copy_template_lines(sub: Subscription, template) -> None:
    for tl in template.lines.select_related("product", "variant"):
        SubscriptionLine.objects.create(
            subscription=sub, product=tl.product, variant=tl.variant,
            quantity=max(tl.quantity, sub.plan.minimum_quantity),
            unit_price=tl.unit_price,  # snapshot, not a live link
        )
    sub.recalculate()


@transaction.atomic
def add_line(*, sub, product, quantity=1, variant=None, tax_rule=None, actor,
             unit_price: Decimal | None = None) -> SubscriptionLine:
    _require_staff(actor)
    if sub.stage not in (Stage.DRAFT, Stage.QUOTATION):
        raise ValidationError({"subscription": "Lines of a confirmed subscription are immutable."})
    if quantity < sub.plan.minimum_quantity:
        raise ValidationError({"quantity": f"Plan requires a minimum quantity of {sub.plan.minimum_quantity}."})
    price = unit_price if unit_price is not None else (
        variant.effective_price if variant else product.sales_price
    )
    line = SubscriptionLine(
        subscription=sub, product=product, variant=variant, quantity=quantity,
        unit_price=price, tax_rule=tax_rule,
    )
    line.full_clean(exclude=["subscription"])
    line.save()
    sub.recalculate()
    return line


@transaction.atomic
def remove_line(*, sub, line_id: int, actor) -> None:
    _require_staff(actor)
    if sub.stage not in (Stage.DRAFT, Stage.QUOTATION):
        raise ValidationError("Lines of a confirmed subscription are immutable.")
    deleted, _ = sub.lines.filter(pk=line_id).delete()
    if not deleted:
        raise ValidationError({"line": "Line not found on this subscription."})
    sub.recalculate()


# ---------------------------------------------------------------------------
# stage machine
# ---------------------------------------------------------------------------

@transaction.atomic
def send_quotation(*, sub, actor, on: date | None = None) -> Subscription:
    """Draft -> Quotation. Needs at least one line; sets validity from template."""
    _require_staff(actor)
    on = on or date.today()
    _check_transition(sub, Stage.QUOTATION)
    if not sub.lines.exists():
        raise ValidationError({"lines": "A quotation must contain at least one line."})
    if sub.origin_template:
        validity_days = sub.origin_template.validity_days
    else:
        validity_days = 14
    sub.validity_until = on + timedelta(days=validity_days)
    _transition(sub, Stage.QUOTATION)
    sub.save(update_fields=["validity_until", "updated_at"])
    return sub


@transaction.atomic
def confirm(*, sub, actor, on: date | None = None) -> Subscription:
    """Quotation -> Confirmed. Refuses if validity lapsed or plan left availability."""
    _require_staff(actor)
    on = on or date.today()
    _check_transition(sub, Stage.CONFIRMED)
    if not sub.lines.exists():
        raise ValidationError({"lines": "Cannot confirm a subscription without lines."})
    if sub.validity_until and on > sub.validity_until:
        raise ValidationError(
            {"validity_until": "Quotation validity lapsed; send a fresh quotation."}
        )
    if not sub.plan.is_selectable(on):
        raise ValidationError({"plan": "Plan is no longer selectable; quote cannot be confirmed."})
    _transition(sub, Stage.CONFIRMED)
    return sub


@transaction.atomic
def activate(*, sub, actor, start_date: date | None = None,
             expiry_date: date | None = None) -> Subscription:
    """Confirmed -> Active. start/expiry may be overridden here, but stay ordered."""
    _require_staff(actor)
    _check_transition(sub, Stage.ACTIVE)
    if start_date:
        sub.start_date = start_date
    if expiry_date:
        sub.expiry_date = expiry_date
    if sub.expiry_date <= sub.start_date:
        raise ValidationError({"expiry_date": "Expiry must be after the start date."})
    sub.full_clean(exclude=["lines"])
    _transition(sub, Stage.ACTIVE)
    return sub


@transaction.atomic
def close(*, sub, actor, reason: str = "Closed by operator",
          on: date | None = None) -> Subscription:
    """
    -> Closed from any open stage. Closing an ACTIVE term early requires the
    plan to allow it; at/after expiry it is always allowed (that's term end).
    """
    _require_staff(actor)
    on = on or date.today()
    if sub.stage == Stage.CLOSED:
        raise InvalidTransition(sub, Stage.CLOSED, "already closed")
    if sub.stage == Stage.ACTIVE and on < sub.expiry_date and not sub.plan.allow_early_close:
        raise InvalidTransition(sub, Stage.CLOSED,
                                "plan does not allow early closure and the term has not ended")
    sub.closed_reason = reason
    sub.is_paused = False
    _close_open_pause(sub, on)
    _transition(sub, Stage.CLOSED)
    return sub


@transaction.atomic
def renew(*, sub, actor, on: date | None = None) -> Subscription:
    """
    One more full period. Requires plan.allow_renew.
    - ACTIVE: extend expiry by one period (never resurrects an already-lapsed
      active term mid-billing — that's reactivation below).
    - CLOSED: only if the term had ended (renew-after-expiry), re-opens as
      Active with a fresh period.
    """
    _require_staff(actor)
    on = on or date.today()
    if not sub.plan.allow_renew:
        raise InvalidTransition(sub, Stage.ACTIVE, "plan does not allow renewal")
    if sub.stage == Stage.ACTIVE:
        sub.expiry_date = advance(sub.expiry_date, sub.plan.billing_frequency)
        sub.save(update_fields=["expiry_date", "updated_at"])
        return sub
    if sub.stage == Stage.CLOSED:
        if on < sub.expiry_date:
            raise InvalidTransition(
                sub, Stage.ACTIVE, "closed before term end — reopen is not a renewal"
            )
        sub.start_date = on
        sub.expiry_date = advance(on, sub.plan.billing_frequency)
        sub.stage = Stage.ACTIVE
        sub.closed_reason = ""
        sub.save(update_fields=["start_date", "expiry_date", "stage", "closed_reason", "updated_at"])
        return sub
    raise InvalidTransition(sub, Stage.ACTIVE, f"cannot renew from {sub.stage}")


@transaction.atomic
def set_paused(*, sub, actor, paused: bool, on: date | None = None) -> Subscription:
    """
    Pause/resume an Active subscription, recording the span.

    The span — not the boolean — is what billing consults: every period that
    overlaps a pause is dropped, so resuming never back-bills suspended months.
    """
    _require_staff(actor)
    on = on or date.today()
    locked = Subscription.objects.select_for_update().get(pk=sub.pk)
    if locked.stage != Stage.ACTIVE:
        raise InvalidTransition(locked, locked.stage,
                                "only Active subscriptions can be paused/resumed")
    if paused and not locked.plan.allow_pause:
        raise InvalidTransition(locked, locked.stage, "plan does not allow pausing")

    if paused and not locked.is_paused:
        PausePeriod.objects.create(subscription=locked, started_on=on)
    elif not paused and locked.is_paused:
        span = (
            locked.pause_periods.filter(ended_on__isnull=True)
            .order_by("-started_on")
            .first()
        )
        if span is not None:
            if on < span.started_on:
                raise ValidationError(
                    {"on": "A pause cannot end before it started."}
                )
            span.ended_on = on
            span.save(update_fields=["ended_on"])

    locked.is_paused = paused
    locked.save(update_fields=["is_paused", "updated_at"])
    return _sync_back(sub, locked)


@transaction.atomic
def auto_close_expired(*, on: date | None = None) -> list[Subscription]:
    """
    Scheduled sweep: subscriptions on plans with auto_close_on_expiry that have
    reached their expiry date are closed. Other expired Actives stay open until
    someone closes or renews them (plan decides).
    """
    on = on or date.today()
    closed = []
    qs = (
        Subscription.objects.filter(
            stage=Stage.ACTIVE, expiry_date__lte=on, plan__auto_close_on_expiry=True
        )
        .select_for_update(of=("self",))
        .select_related("plan")
        .order_by("pk")
    )
    for sub in qs:
        sub.closed_reason = "Auto-closed at term expiry"
        sub.stage = Stage.CLOSED
        sub.is_paused = False
        _close_open_pause(sub, on)
        sub.save(update_fields=["stage", "closed_reason", "is_paused", "updated_at"])
        closed.append(sub)
    return closed
