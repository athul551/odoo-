from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.billing.models import Invoice

ZERO = Decimal("0.00")


class Payment(models.Model):
    """
    Money recorded against exactly one invoice: method, amount, date, note.
    Amounts are aggregated (not hand-tracked) by payments.services to derive
    an invoice's amount_paid and status — the ledger rows are the truth.
    """

    class Method(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        CARD = "card", "Card"
        CASH = "cash", "Cash"
        CHECK = "check", "Check"
        OTHER = "other", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    paid_on = models.DateField(default=date.today)
    reference = models.CharField(max_length=100, blank=True, help_text="Bank/ref number")
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="payments_recorded"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=ZERO), name="payment_amount_positive"
            ),
        ]
        indexes = [
            # revenue window: WHERE paid_on BETWEEN start AND end
            models.Index(fields=["paid_on"], name="payment_paid_on_idx"),
            models.Index(fields=["invoice", "paid_on"], name="payment_invoice_date_idx"),
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount} on {self.paid_on} -> {self.invoice.number}"
