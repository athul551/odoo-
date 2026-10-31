"""
Payments are the ledger truth. Every record/removal locks the invoice,
recomputes amount_paid from the rows themselves, and derives the status:
confirmed invoice + fully covered payments -> Paid. Removing payments that
covered an invoice drops it back to Confirmed (never silently to Draft).
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.billing.models import Invoice

from .models import Payment

ZERO = Decimal("0.00")


def _require_staff(actor):
    if not getattr(actor, "is_member_of_staff", False):
        raise PermissionDenied("Only admin or staff may record payments.")


@transaction.atomic
def record_payment(*, invoice: Invoice, actor, amount: Decimal, method: str,
                   paid_on: date | None = None, reference: str = "", note: str = "") -> Payment:
    _require_staff(actor)
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status == Invoice.Status.DRAFT:
        raise ValidationError({"invoice": "Cannot receive payment against a draft invoice."})
    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError({"invoice": "Cannot receive payment against a cancelled invoice."})
    if amount <= 0:
        raise ValidationError({"amount": "Payment amount must be positive."})

    due = invoice.total - invoice.amount_paid
    if amount > due:
        raise ValidationError(
            {"amount": f"Overpayment refused: only {due} remains due on {invoice.number}."}
        )

    payment = Payment.objects.create(
        invoice=invoice, method=method, amount=amount,
        paid_on=paid_on or date.today(), reference=reference, note=note,
        recorded_by=actor if getattr(actor, "pk", None) else None,
    )
    _resync(invoice)
    return payment


@transaction.atomic
def remove_payment(*, payment: Payment, actor) -> None:
    """Undo a mis-recorded payment; re-derives invoice status. Periods of
    cancelled invoices then become billable again via the billing run."""
    _require_staff(actor)
    invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
    if payment.method and invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError(
            {"invoice": "Invoice already cancelled; its payment records are frozen."}
        )
    payment.delete()
    _resync(invoice)


def _resync(invoice: Invoice) -> Invoice:
    total_paid = invoice.payments.aggregate(s=Sum("amount"))["s"] or ZERO
    invoice.amount_paid = total_paid
    if invoice.status != Invoice.Status.CANCELLED:
        if total_paid >= invoice.total and invoice.total > ZERO:
            invoice.status = Invoice.Status.PAID
        elif invoice.status == Invoice.Status.PAID:
            invoice.status = Invoice.Status.CONFIRMED
    invoice.save(update_fields=["amount_paid", "status", "updated_at"])
    return invoice
