from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class QuotationTemplate(models.Model):
    """
    Reusable blueprint: a plan plus product lines, with a validity window in
    days. A sales rep starts a Subscription from a template instead of
    rebuilding the same offer from scratch.
    """

    name = models.CharField(max_length=255, unique=True)
    plan = models.ForeignKey(
        "products.Plan", on_delete=models.PROTECT, related_name="quotation_templates"
    )
    validity_days = models.PositiveIntegerField(default=14)
    payment_terms_days = models.PositiveIntegerField(default=30)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(validity_days__gte=1), name="template_validity_positive"
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        if not self.name or not self.name.strip():
            errors["name"] = "Template name is required."
        if self.validity_days is not None and self.validity_days < 1:
            errors["validity_days"] = "Validity must be at least one day."
        if not self.plan_id:
            errors["plan"] = "A template must reference a plan."
        elif not self.plan.active:
            errors["plan"] = "An inactive plan cannot be quoted from a template."
        if errors:
            raise ValidationError(errors)


class QuotationTemplateLine(models.Model):
    """One product/variant/quantity the template proposes."""

    template = models.ForeignKey(
        QuotationTemplate, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="template_lines"
    )
    variant = models.ForeignKey(
        "products.ProductVariant", null=True, blank=True,
        on_delete=models.PROTECT, related_name="template_lines",
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "product", "variant"], name="template_line_unique"
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=1), name="template_line_quantity_positive"
            ),
        ]
        ordering = ["product__name"]

    def __str__(self):
        suffix = f" ({self.variant})" if self.variant else ""
        return f"{self.product.name}{suffix} x{self.quantity}"

    def clean(self):
        super().clean()
        if self.variant_id and self.variant.product_id != self.product_id:
            raise ValidationError(
                {"variant": "Variant must belong to the same product as the line."}
            )
        if not self.product.active:
            raise ValidationError({"product": "Cannot quote an inactive product."})

    @property
    def unit_price(self) -> Decimal:
        if self.variant:
            return self.variant.effective_price
        return self.product.sales_price
