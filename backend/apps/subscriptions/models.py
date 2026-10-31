from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.timeutils import advance
from apps.customers.models import Customer
from apps.products.models import Plan, Product, ProductVariant

ZERO = Decimal("0.00")


class InvalidTransition(Exception):
    """Raised when a requested stage move is not legal for the subscription."""

    def __init__(self, subscription, attempted: str, reason: str):
        self.subscription = subscription
        self.attempted = attempted
        self.reason = reason
        super().__init__(
            f"Subscription {subscription.number}: cannot go from "
            f"{subscription.stage} to {attempted}: {reason}"
        )


class Subscription(models.Model):
    """
    The central contract. Linear, never-backward stage machine (CONTEXT.md):

        Draft -> Quotation -> Confirmed -> Active -> Closed
        (Draft/Quotation/Confirmed may also be Closed directly.)

    All state moves go through subscriptions.services, which validates plan
    behavior flags, actor roles and line integrity before touching the stage.
    """

    class Stage(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUOTATION = "quotation", "Quotation"
        CONFIRMED = "confirmed", "Confirmed"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    number = models.CharField(max_length=32, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.DRAFT)

    start_date = models.DateField()
    expiry_date = models.DateField()
    validity_until = models.DateField(null=True, blank=True)  # set when Quotation sent
    payment_terms_days = models.PositiveIntegerField(default=30)
    origin_template = models.ForeignKey(
        "quotations.QuotationTemplate", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="subscriptions",
    )

    is_paused = models.BooleanField(default=False)
    closed_reason = models.CharField(max_length=255, blank=True)

    # denormalised totals kept in sync by recalculate() — reports read these
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="subscriptions_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(expiry_date__gt=models.F("start_date")),
                name="subscription_expiry_after_start",
            ),
            models.CheckConstraint(
                check=models.Q(subtotal__gte=ZERO) & models.Q(tax_total__gte=ZERO) & models.Q(total__gte=ZERO),
                name="subscription_totals_non_negative",
            ),
        ]
        indexes = [
            # billing-day scan: ACTIVE, unpaused, not yet expired
            models.Index(fields=["stage", "is_paused", "expiry_date"], name="sub_billing_scan_idx"),
            # portal/dashboard slice by customer
            models.Index(fields=["customer", "stage"], name="sub_customer_stage_idx"),
        ]

    def __str__(self):
        return f"{self.number} — {self.customer.name}"

    @property
    def is_expired(self) -> bool:
        return date.today() >= self.expiry_date

    def clean(self):
        super().clean()
        errors = {}
        if self.expiry_date and self.start_date and self.expiry_date <= self.start_date:
            errors["expiry_date"] = "Expiry must be after the start date."
        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------
    # amount machinery
    # ------------------------------------------------------------------
    def recalculate(self, *, save: bool = True) -> None:
        subtotal = ZERO
        tax_total = ZERO
        for line in self.lines.select_related("tax_rule"):
            subtotal += line.amount
            tax_total += line.tax_amount
        self.subtotal, self.tax_total, self.total = subtotal, tax_total, subtotal + tax_total
        if save:
            self.save(update_fields=["subtotal", "tax_total", "total", "updated_at"])


class PausePeriod(models.Model):
    """
    A span during which service — and therefore billing — was suspended.

    Pausing is *not* a deferral: a period that overlaps a pause is never
    billed, not even after the subscription resumes. The spans are the truth;
    ``Subscription.is_paused`` is only the "a span is open right now" flag the
    UI and API read.
    """

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="pause_periods"
    )
    started_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)  # null = still paused
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["started_on"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(ended_on__isnull=True)
                | models.Q(ended_on__gte=models.F("started_on")),
                name="pause_period_not_inverted",
            ),
        ]

    def __str__(self):
        end = self.ended_on.isoformat() if self.ended_on else "…"
        return f"{self.subscription.number}: paused {self.started_on} → {end}"

    @property
    def is_open(self) -> bool:
        return self.ended_on is None

    def overlaps(self, start: date, end: date) -> bool:
        """Does the half-open period [start, end) touch this pause at all?"""
        span_end = self.ended_on or date.max
        if span_end <= self.started_on:  # a same-day pause is empty, not a gap
            return False
        return self.started_on < end and start < span_end


class SubscriptionLine(models.Model):
    """
    Product line with price/tax snapshots. (product, variant) is unique per
    subscription; quantity >= 1; unit_price frozen at creation time.
    """

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="subscription_lines")
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True, on_delete=models.PROTECT,
        related_name="subscription_lines",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    tax_rule = models.ForeignKey(
        "billing.TaxRule", null=True, blank=True, on_delete=models.PROTECT,
        related_name="subscription_lines",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO, editable=False)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "product"],
                condition=models.Q(variant__isnull=True),
                name="line_one_per_product_without_variant",
            ),
            models.UniqueConstraint(
                fields=["subscription", "product", "variant"],
                name="line_one_per_product_variant",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=1), name="line_quantity_positive"
            ),
            models.CheckConstraint(
                check=models.Q(unit_price__gte=ZERO), name="line_unit_price_non_negative"
            ),
        ]
        ordering = ["product__name"]

    def __str__(self):
        suffix = f" ({self.variant})" if self.variant else ""
        return f"{self.product.name}{suffix} x{self.quantity}"

    def clean(self):
        super().clean()
        if self.variant_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "Variant must belong to the line's product."})
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})
        if self.subscription_id and self.subscription.stage not in (
            Subscription.Stage.DRAFT, Subscription.Stage.QUOTATION
        ):
            raise ValidationError(
                {"subscription": "Lines of a confirmed subscription are immutable."}
            )

    def save(self, *args, **kwargs):
        self.amount = (self.unit_price * self.quantity).quantize(Decimal("0.01"))
        rate = self.tax_rule.rate if self.tax_rule_id else Decimal("0")
        self.tax_amount = (self.amount * rate / Decimal("100")).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
