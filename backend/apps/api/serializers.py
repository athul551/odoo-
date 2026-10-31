"""
Serializers for every domain resource.

Two rules hold throughout:

* **Reads** are shaped for the SPA (names alongside ids, money as strings via
  DRF's DecimalField, no N+1 thanks to queryset scoping in the viewsets).
* **Writes** never bypass the domain layer. Where a service exists
  (subscriptions, invoices, payments, discounts) the serializer's ``create``
  calls it, so role gates, stage rules and ledger maths stay in one place.
  Plain CRUD (customers, catalog) still runs ``full_clean()`` — the same
  model rules the DB constraints backstop.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.billing.models import (
    AppliedDiscount,
    BillingRun,
    DiscountRule,
    Invoice,
    InvoiceLine,
    TaxRule,
)
from apps.billing.services import create_discount_rule
from apps.customers.models import Customer
from apps.payments.models import Payment
from apps.payments.services import record_payment
from apps.products.models import Plan, Product, ProductVariant
from apps.quotations.models import QuotationTemplate, QuotationTemplateLine
from apps.subscriptions.models import Subscription, SubscriptionLine
from apps.subscriptions.services import add_line, create_subscription


def full_clean(instance, *, exclude=()):
    """Run the model's own validation and re-raise it in DRF's dialect."""
    try:
        instance.full_clean(exclude=list(exclude))
    except DjangoValidationError as exc:
        raise serializers.ValidationError(
            exc.message_dict
            if hasattr(exc, "message_dict")
            else {"non_field_errors": exc.messages}
        )


class ModelBooleanField(serializers.BooleanField):
    """
    An absent key means "not supplied", not "unchecked".

    DRF's HTML form handling turns an omitted boolean into False, which would
    silently switch off plan behaviors (or archive a product) for any client
    posting form data. The API is JSON-first, so the documented default wins
    and a client that really means False sends ``false`` explicitly.
    """

    default_empty_html = serializers.empty


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

class CustomerSerializer(serializers.ModelSerializer):
    subscription_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Customer
        fields = [
            "id", "name", "contact_email", "phone", "address_line", "city",
            "postal_code", "country", "tax_id", "notes", "subscription_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Customer name is required.")
        return value.strip()

    def create(self, validated_data):
        customer = Customer(**validated_data)
        full_clean(customer)
        customer.save()
        return customer

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        full_clean(instance)
        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class ProductVariantSerializer(serializers.ModelSerializer):
    effective_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = ProductVariant
        fields = ["id", "attribute", "value", "price_delta", "active", "effective_price"]
        read_only_fields = ["id", "effective_price"]

    def validate_price_delta(self, value: Decimal) -> Decimal:
        return value


class ProductSerializer(serializers.ModelSerializer):
    """
    Nested variants are *replace* semantics on write: unknown axis/value pairs
    are created, existing ones updated, and omitted ones deactivated (never
    deleted — subscription lines PROTECT them so history stays readable).
    """

    variants = ProductVariantSerializer(many=True, required=False)
    active = ModelBooleanField(default=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "type", "sales_price", "cost_price", "notes", "active",
            "variants", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    @transaction.atomic
    def create(self, validated_data):
        variants = validated_data.pop("variants", [])
        product = Product(**validated_data)
        full_clean(product)
        product.save()
        self._sync_variants(product, variants)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        variants = validated_data.pop("variants", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        full_clean(instance)
        instance.save()
        if variants is not None:
            self._sync_variants(instance, variants)
        return instance

    def _sync_variants(self, product: Product, rows: list[dict]) -> None:
        seen = set()
        for row in rows:
            attribute, value = row["attribute"].strip(), row["value"].strip()
            variant = (
                ProductVariant.objects.filter(
                    product=product, attribute=attribute, value=value
                ).first()
                or ProductVariant(product=product, attribute=attribute, value=value)
            )
            variant.price_delta = row.get("price_delta", variant.price_delta)
            variant.active = row.get("active", True)
            full_clean(variant)
            variant.save()
            seen.add((attribute, value))
        for variant in product.variants.all():
            if (variant.attribute, variant.value) not in seen and variant.active:
                variant.active = False
                variant.save(update_fields=["active"])


class PlanSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    # Explicit defaults: form-encoded clients otherwise get False from DRF's
    # HTML boolean handling, which would silently disable a plan's behaviors.
    auto_close_on_expiry = ModelBooleanField(default=False)
    allow_early_close = ModelBooleanField(default=True)
    allow_pause = ModelBooleanField(default=True)
    allow_renew = ModelBooleanField(default=True)
    active = ModelBooleanField(default=True)
    is_selectable = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "id", "product", "product_name", "name", "billing_frequency", "price",
            "minimum_quantity", "availability_start", "availability_end",
            "auto_close_on_expiry", "allow_early_close", "allow_pause", "allow_renew",
            "active", "notes", "is_selectable", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_is_selectable(self, obj: Plan) -> bool:
        return obj.is_selectable()

    def create(self, validated_data):
        plan = Plan(**validated_data)
        full_clean(plan)
        plan.save()
        return plan

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        full_clean(instance)
        instance.save()
        return instance


class TaxRuleSerializer(serializers.ModelSerializer):
    active = ModelBooleanField(default=True)

    class Meta:
        model = TaxRule
        fields = ["id", "name", "rate", "active"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        rule = TaxRule(**validated_data)
        full_clean(rule)
        rule.save()
        return rule

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        full_clean(instance)
        instance.save()
        return instance


class QuotationTemplateLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = QuotationTemplateLine
        fields = ["id", "product", "variant", "quantity", "product_name", "unit_price"]
        read_only_fields = ["id", "product_name", "unit_price"]


class QuotationTemplateSerializer(serializers.ModelSerializer):
    lines = QuotationTemplateLineSerializer(many=True, required=False)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    active = ModelBooleanField(default=True)

    class Meta:
        model = QuotationTemplate
        fields = [
            "id", "name", "plan", "plan_name", "validity_days", "payment_terms_days",
            "notes", "active", "lines", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        template = QuotationTemplate(**validated_data)
        full_clean(template)
        template.save()
        self._sync_lines(template, lines)
        return template

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        full_clean(instance)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            self._sync_lines(instance, lines)
        return instance

    def _sync_lines(self, template, rows):
        for row in rows:
            line = QuotationTemplateLine(template=template, **row)
            full_clean(line)
            line.save()


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class SubscriptionLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    variant_label = serializers.SerializerMethodField()
    tax_rate = serializers.DecimalField(
        source="tax_rule.rate", max_digits=6, decimal_places=3, read_only=True
    )

    class Meta:
        model = SubscriptionLine
        fields = [
            "id", "product", "product_name", "variant", "variant_label", "quantity",
            "unit_price", "tax_rule", "tax_rate", "amount", "tax_amount",
        ]
        read_only_fields = fields

    def get_variant_label(self, obj: SubscriptionLine) -> str | None:
        if not obj.variant_id:
            return None
        return f"{obj.variant.attribute}={obj.variant.value}"


class SubscriptionSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    billing_frequency = serializers.CharField(
        source="plan.billing_frequency", read_only=True
    )
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    lines = SubscriptionLineSerializer(many=True, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    invoice_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Subscription
        fields = [
            "id", "number", "customer", "customer_name", "plan", "plan_name",
            "billing_frequency", "stage", "stage_display", "start_date",
            "expiry_date", "validity_until", "payment_terms_days", "is_paused",
            "is_expired", "closed_reason", "subtotal", "tax_total", "total",
            "invoice_count", "lines", "created_at", "updated_at",
        ]
        read_only_fields = fields


class SubscriptionLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(), required=False, allow_null=True
    )
    quantity = serializers.IntegerField(min_value=1, default=1)
    tax_rule = serializers.PrimaryKeyRelatedField(
        queryset=TaxRule.objects.all(), required=False, allow_null=True
    )
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.00")
    )

    def validate(self, attrs):
        variant = attrs.get("variant")
        if variant and variant.product_id != attrs["product"].id:
            raise serializers.ValidationError(
                {"variant": ["Variant must belong to the line's product."]}
            )
        return attrs


class SubscriptionCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    plan = serializers.PrimaryKeyRelatedField(queryset=Plan.objects.all())
    start_date = serializers.DateField()
    expiry_date = serializers.DateField(required=False, allow_null=True)
    payment_terms_days = serializers.IntegerField(min_value=0, max_value=365, default=30)
    origin_template = serializers.PrimaryKeyRelatedField(
        queryset=QuotationTemplate.objects.all(), required=False, allow_null=True
    )
    lines = SubscriptionLineInputSerializer(many=True, required=False)

    def validate(self, attrs):
        template = attrs.get("origin_template")
        if template is not None and template.plan_id != attrs["plan"].id:
            raise serializers.ValidationError(
                {"origin_template": ["Template belongs to a different plan."]}
            )
        expiry = attrs.get("expiry_date")
        if expiry is not None and expiry <= attrs["start_date"]:
            raise serializers.ValidationError(
                {"expiry_date": ["Expiry must be after the start date."]}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        actor = self.context["request"].user
        subscription = create_subscription(actor=actor, **validated_data)
        for line in lines:
            add_line(sub=subscription, actor=actor, **line)
        return subscription


class SubscriptionTransitionSerializer(serializers.Serializer):
    """Body of every stage action; each service picks the fields it needs."""

    on = serializers.DateField(required=False)
    start_date = serializers.DateField(required=False)
    expiry_date = serializers.DateField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class SubscriptionUpdateSerializer(serializers.Serializer):
    """The only fields an operator may edit in place; stages move via actions."""

    start_date = serializers.DateField(required=False)
    expiry_date = serializers.DateField(required=False)
    payment_terms_days = serializers.IntegerField(required=False, min_value=0, max_value=365)


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id", "description", "quantity", "unit_price", "tax_rate", "base_amount",
            "discount", "amount", "tax_amount",
        ]
        read_only_fields = fields


class AppliedDiscountSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)

    class Meta:
        model = AppliedDiscount
        fields = ["id", "rule", "rule_name", "line", "amount"]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    recorded_by_email = serializers.CharField(source="recorded_by.email", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "invoice", "invoice_number", "method", "amount", "paid_on",
            "reference", "note", "recorded_by", "recorded_by_email", "created_at",
        ]
        read_only_fields = ["id", "invoice", "invoice_number", "recorded_by",
                            "recorded_by_email", "created_at"]


class PaymentCreateSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    paid_on = serializers.DateField(required=False)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        return record_payment(actor=self.context["request"].user, **validated_data)


class InvoiceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    subscription_number = serializers.CharField(
        source="subscription.number", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    amount_due = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    is_overdue = serializers.SerializerMethodField()
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    applied_discounts = AppliedDiscountSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "subscription", "subscription_number", "customer",
            "customer_name", "status", "status_display", "period_start",
            "period_end", "issued_at", "due_date", "sent_at", "printed_at",
            "subtotal", "discount_total", "tax_total", "total", "amount_paid",
            "amount_due", "is_overdue", "lines", "payments", "applied_discounts",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_overdue(self, obj: Invoice) -> bool:
        return obj.is_overdue()


class InvoiceListSerializer(serializers.ModelSerializer):
    """Light shape for tables: no line/payment payload."""

    customer_name = serializers.CharField(source="customer.name", read_only=True)
    subscription_number = serializers.CharField(
        source="subscription.number", read_only=True
    )
    amount_due = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "customer", "customer_name", "subscription_number",
            "status", "period_start", "period_end", "due_date", "total",
            "amount_paid", "amount_due",
        ]
        read_only_fields = fields


class DiscountRuleSerializer(serializers.ModelSerializer):
    usage_count = serializers.SerializerMethodField()

    class Meta:
        model = DiscountRule
        fields = [
            "id", "name", "scope", "kind", "value", "minimum_amount",
            "minimum_quantity", "applies_from", "applies_until", "usage_limit",
            "products", "subscriptions", "active", "usage_count", "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "usage_count"]

    def get_usage_count(self, obj: DiscountRule) -> int:
        return obj.usage()


class DiscountRuleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    scope = serializers.ChoiceField(choices=DiscountRule.Scope.choices)
    kind = serializers.ChoiceField(choices=DiscountRule.Kind.choices)
    value = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00")
    )
    applies_from = serializers.DateField()
    applies_until = serializers.DateField(required=False, allow_null=True)
    minimum_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0.00"),
    )
    minimum_quantity = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    usage_limit = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    product_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    subscription_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if attrs["kind"] == DiscountRule.Kind.PERCENT and attrs["value"] > 100:
            raise serializers.ValidationError(
                {"value": ["A percentage discount cannot exceed 100%."]}
            )
        if attrs.get("applies_until") and attrs["applies_until"] < attrs["applies_from"]:
            raise serializers.ValidationError(
                {"applies_until": ["Window end cannot precede window start."]}
            )
        if attrs.get("product_ids") and attrs["scope"] != DiscountRule.Scope.PRODUCT:
            raise serializers.ValidationError(
                {"product_ids": ["Products require a product-scoped rule."]}
            )
        if attrs.get("subscription_ids") and attrs["scope"] != DiscountRule.Scope.SUBSCRIPTION:
            raise serializers.ValidationError(
                {"subscription_ids": ["Subscriptions require a subscription-scoped rule."]}
            )
        return attrs

    def create(self, validated_data):
        return create_discount_rule(
            actor=self.context["request"].user, **validated_data
        )


class BillingRunSerializer(serializers.ModelSerializer):
    invoice_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = BillingRun
        fields = [
            "id", "ran_on", "started_at", "finished_at", "billed_count",
            "skipped_count", "report", "invoice_count",
        ]
        read_only_fields = fields


class BillingRunRequestSerializer(serializers.Serializer):
    on = serializers.DateField(required=False)
    dry_run = serializers.BooleanField(required=False, default=False)
