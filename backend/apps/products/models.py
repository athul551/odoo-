from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.timeutils import Frequency, advance


class Product(models.Model):
    """A sellable offering: name, type, sales price, cost price, notes."""

    class Type(models.TextChoices):
        GOODS = "goods", "Goods"
        SERVICE = "service", "Service"
        ADDON = "addon", "Add-on"

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.SERVICE)
    sales_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Product name is required."})


class ProductVariant(models.Model):
    """
    One configuration axis of a product, e.g. attribute 'brand', value 'Odoo',
    price delta +560. Effective price = product.sales_price + price_delta and
    must never be negative (checked here; deltas can be negative for downgrades).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    attribute = models.CharField(max_length=100, help_text="e.g. brand")
    value = models.CharField(max_length=100, help_text="e.g. Odoo")
    price_delta = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Added to the product sales price when this variant is chosen",
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product__name", "attribute", "value"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "attribute", "value"], name="variant_axis_value_unique"
            ),
        ]

    def __str__(self):
        return f"{self.product.name}: {self.attribute}={self.value}"

    @property
    def effective_price(self) -> Decimal:
        return self.product.sales_price + self.price_delta

    def clean(self):
        super().clean()
        if self.product_id is not None and self.effective_price < 0:
            raise ValidationError(
                {"price_delta": f"Variant price would be {self.effective_price}; must be >= 0."}
            )
        if not self.value.strip():
            raise ValidationError({"value": "Variant value is required."})


class Plan(models.Model):
    """
    Recurring billable offering belonging to a Product.

    The availability window governs *selection* of new subscriptions only;
    existing subscriptions keep billing after the window closes.
    Plan Behaviors decide, per plan: auto-close on expiry, early close,
    pause, renew.
    """

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="plans")
    name = models.CharField(max_length=255)
    billing_frequency = models.CharField(max_length=10, choices=Frequency.CHOICES)
    price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    minimum_quantity = models.PositiveIntegerField(default=1)
    availability_start = models.DateField()
    availability_end = models.DateField(null=True, blank=True, help_text="Open-ended if empty")

    # Plan Behaviors
    auto_close_on_expiry = models.BooleanField(default=False)
    allow_early_close = models.BooleanField(default=True)
    allow_pause = models.BooleanField(default=True)
    allow_renew = models.BooleanField(default=True)

    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="plan_name_per_product"),
            models.CheckConstraint(
                check=models.Q(availability_end__isnull=True)
                | models.Q(availability_end__gte=models.F("availability_start")),
                name="plan_availability_window_ordered",
            ),
            models.CheckConstraint(
                check=models.Q(minimum_quantity__gte=1), name="plan_minimum_quantity_positive"
            ),
            models.CheckConstraint(
                check=models.Q(price__gte=Decimal("0.00")), name="plan_price_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_billing_frequency_display()})"

    def is_selectable(self, on: date | None = None) -> bool:
        """May this plan be chosen for a NEW subscription on the given date?"""
        on = on or date.today()
        if not self.active:
            return False
        if on < self.availability_start:
            return False
        if self.availability_end and on > self.availability_end:
            return False
        return True

    def next_period_start(self, current_start, periods: int = 1):
        """Calendar-safe period advance anchored on this plan's frequency."""
        return advance(current_start, self.billing_frequency, periods)

    def clean(self):
        super().clean()
        errors = {}
        if not self.name or not self.name.strip():
            errors["name"] = "Plan name is required."
        if self.availability_end and self.availability_start and (
            self.availability_end < self.availability_start
        ):
            errors["availability_end"] = "Availability end cannot precede availability start."
        if errors:
            raise ValidationError(errors)
