from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.customers.models import Customer

ZERO = Decimal("0.00")


class TaxRule(models.Model):
    """Admin-set tax used to compute invoice/line tax automatically."""

    name = models.CharField(max_length=100, unique=True)
    rate = models.DecimalField(
        max_digits=6, decimal_places=3,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(check=models.Q(rate__gte=Decimal("0")), name="tax_rate_non_negative"),
            models.CheckConstraint(check=models.Q(rate__lte=Decimal("100")), name="tax_rate_max_100"),
        ]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class BillingRun(models.Model):
    """Audit record of one billing-day batch (ADR 0001)."""

    ran_on = models.DateField()
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    billed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    report = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-ran_on", "-started_at"]

    def __str__(self):
        return f"BillingRun {self.ran_on} (billed={self.billed_count}, skipped={self.skipped_count})"


class Invoice(models.Model):
    """
    Draft -> Confirmed -> Paid, with Cancel as an exit from any of those
    (paid/cancelled-after-payments guarded via attached payments, ADR 0002).

    Exactly one non-cancelled invoice may exist per (subscription, period) —
    enforced by a partial unique index, the heart of ADR 0001.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=32, unique=True, editable=False)
    subscription = models.ForeignKey("subscriptions.Subscription", on_delete=models.PROTECT,
                                     related_name="invoices")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    run = models.ForeignKey(
        BillingRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices"
    )

    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)

    issued_at = models.DateTimeField(null=True, blank=True)   # set on confirm
    due_date = models.DateField(null=True, blank=True)        # issued_at + payment terms
    sent_at = models.DateTimeField(null=True, blank=True)
    printed_at = models.DateTimeField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    OPEN_STATUSES = (Status.DRAFT, Status.CONFIRMED, Status.PAID)

    class Meta:
        ordering = ["-period_start", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "period_start"],
                condition=Q(status__in=["draft", "confirmed", "paid"]),
                name="invoice_one_per_subscription_period",
            ),
            models.CheckConstraint(
                check=models.Q(period_end__gt=models.F("period_start")),
                name="invoice_period_ordered",
            ),
            models.CheckConstraint(
                check=(models.Q(subtotal__gte=ZERO) & models.Q(tax_total__gte=ZERO)
                       & models.Q(total__gte=ZERO) & models.Q(amount_paid__gte=ZERO)
                       & models.Q(amount_paid__lte=models.F("total"))
                       & models.Q(discount_total__gte=ZERO)
                       & models.Q(discount_total__lte=models.F("subtotal"))),
                name="invoice_amounts_sane",
            ),
        ]
        indexes = [
            # chase lists: WHERE status = 'confirmed' AND due_date < today
            models.Index(fields=["status", "due_date"], name="invoice_status_due_idx"),
            # customer-scoped dashboards
            models.Index(fields=["customer", "status"], name="invoice_customer_status_idx"),
            # invoiced-total window filter
            models.Index(fields=["issued_at"], name="invoice_issued_at_idx"),
        ]

    def __str__(self):
        return self.number

    @property
    def amount_due(self) -> Decimal:
        return self.total - self.amount_paid

    @property
    def is_outstanding(self) -> bool:
        return self.status == self.Status.CONFIRMED and self.amount_due > 0

    def is_overdue(self, on: date | None = None) -> bool:
        on = on or date.today()
        return self.is_outstanding and self.due_date is not None and self.due_date < on

    def clean(self):
        super().clean()
        errors = {}
        if self.period_end and self.period_start and self.period_end <= self.period_start:
            errors["period_end"] = "Period end must be after period start."
        if errors:
            raise ValidationError(errors)


class InvoiceLine(models.Model):
    """
    Immutable snapshot of one subscription line at issuance: description,
    product refs for traceability, qty, unit price, tax rate/value, amount.
    """

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    product = models.ForeignKey(
        "products.Product", null=True, blank=True, on_delete=models.PROTECT
    )
    variant = models.ForeignKey(
        "products.ProductVariant", null=True, blank=True, on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(
        max_digits=6, decimal_places=3, default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("100"))],
    )
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO, editable=False)
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO, editable=False)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO, editable=False)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO, editable=False)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(discount__gte=ZERO) & models.Q(discount__lte=models.F("base_amount")),
                name="line_discount_between_zero_and_base",
            ),
        ]

    def save(self, *args, **kwargs):
        self.base_amount = (self.unit_price * self.quantity).quantize(Decimal("0.01"))
        self.amount = (self.base_amount - self.discount).quantize(Decimal("0.01"))
        self.tax_amount = (self.amount * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


class DiscountRule(models.Model):
    """
    Admin-only. The discount domain rules are evaluated per Billing Run and
    snapshotted onto the invoice as Applied Discount rows; they are never
    re-evaluated retroactively and never revoked from issued invoices.
    """

    class Scope(models.TextChoices):
        PRODUCT = "product", "Specific products"
        SUBSCRIPTION = "subscription", "Whole subscriptions"

    class Kind(models.TextChoices):
        PERCENT = "percent", "Percentage"
        AMOUNT = "amount", "Fixed amount"

    name = models.CharField(max_length=255, unique=True)
    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.PRODUCT)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(max_digits=12, decimal_places=2,
                                validators=[MinValueValidator(ZERO)])
    minimum_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                         validators=[MinValueValidator(ZERO)])
    minimum_quantity = models.PositiveIntegerField(null=True, blank=True)
    applies_from = models.DateField()
    applies_until = models.DateField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True,
                                              help_text="Max invoices this may hit; empty = unlimited")
    products = models.ManyToManyField("products.Product", blank=True, related_name="discount_rules")
    subscriptions = models.ManyToManyField(
        "subscriptions.Subscription", blank=True, related_name="discount_rules"
    )
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="discount_rules_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(applies_until__isnull=True)
                | models.Q(applies_until__gte=models.F("applies_from")),
                name="discount_window_ordered",
            ),
            models.CheckConstraint(
                check=models.Q(usage_limit__isnull=True) | models.Q(usage_limit__gte=1),
                name="discount_usage_limit_positive",
            ),
            models.CheckConstraint(
                check=models.Q(value__gte=ZERO), name="discount_value_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()} {self.value})"

    def clean(self):
        super().clean()
        errors = {}
        if self.kind == self.Kind.PERCENT and self.value > 100:
            errors["value"] = "A percentage discount cannot exceed 100%."
        if self.applies_until and self.applies_from and self.applies_until < self.applies_from:
            errors["applies_until"] = "Window end cannot precede window start."
        if self.pk is not None:
            if self.scope == self.Scope.PRODUCT and self.subscriptions.exists():
                errors["subscriptions"] = "Product-scoped rules list products, not subscriptions."
            if self.scope == self.Scope.SUBSCRIPTION and self.products.exists():
                errors["products"] = "Subscription-scoped rules list subscriptions, not products."
        if errors:
            raise ValidationError(errors)

    def is_within_window(self, on: date) -> bool:
        if on < self.applies_from:
            return False
        return self.applies_until is None or on <= self.applies_until

    def usage(self) -> int:
        """Invoices (non-cancelled) this rule already hit — its consumed uses."""
        return (
            self.applications.exclude(invoice__status=Invoice.Status.CANCELLED)
            .values("invoice_id").distinct().count()
        )

    def has_capacity(self, on: date) -> bool:
        if not self.active or not self.is_within_window(on):
            return False
        if self.usage_limit is not None and self.usage() >= self.usage_limit:
            return False
        return True

    def value_for(self, base: Decimal) -> Decimal:
        """Discount this rule grants on the given base, capped so nothing goes negative."""
        if self.kind == self.Kind.PERCENT:
            raw = (base * self.value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            raw = self.value
        return min(raw, base) if raw > ZERO else ZERO


class AppliedDiscount(models.Model):
    """
    The snapshot row proving a rule hit this invoice: amount, scope target,
    and (for product scope) the line it reduced. Cancelling the invoice
    releases the rule's use — usage() counts non-cancelled invoices only.
    """

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="applied_discounts")
    rule = models.ForeignKey(DiscountRule, on_delete=models.PROTECT, related_name="applications")
    line = models.ForeignKey(
        InvoiceLine, null=True, blank=True, on_delete=models.CASCADE, related_name="applied_discounts"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=ZERO), name="applied_discount_positive"
            ),
            models.UniqueConstraint(
                fields=["invoice", "rule"],
                condition=Q(line__isnull=True),
                name="one_order_discount_per_invoice_rule",
            ),
            models.UniqueConstraint(
                fields=["invoice", "rule", "line"],
                name="one_line_discount_per_invoice_rule",
            ),
        ]

    def __str__(self):
        target = f"line {self.line_id}" if self.line_id else "invoice"
        return f"{self.rule.name} -> {self.invoice.number} ({target}) = {self.amount}"
