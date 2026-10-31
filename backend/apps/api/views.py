"""
REST surface. Viewsets are thin: validate shape, pick a queryset the caller is
allowed to see, then hand the write to the domain service. Anything else —
role rules, stage machine, ledger maths, discount selection — stays in the
service layer so the API, the admin and the MCP server cannot drift apart.
"""

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.billing import services as billing_services
from apps.billing.models import BillingRun, DiscountRule, Invoice, TaxRule
from apps.common.permissions import (
    IsAdminOnly,
    IsAdminOrReadOnly,
    IsAdminOrStaff,
    IsStaffOrAdminReadAdminWrite,
    StaffWritePortalRead,
)
from apps.customers.models import Customer
from apps.payments import services as payment_services
from apps.payments.models import Payment
from apps.products.models import Plan, Product
from apps.quotations.models import QuotationTemplate
from apps.subscriptions import services as subscription_services
from apps.subscriptions.models import Subscription, SubscriptionLine

from .serializers import (
    BillingRunRequestSerializer,
    BillingRunSerializer,
    CustomerSerializer,
    DiscountRuleCreateSerializer,
    DiscountRuleSerializer,
    InvoiceListSerializer,
    InvoiceSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    PlanSerializer,
    ProductSerializer,
    QuotationTemplateSerializer,
    SubscriptionCreateSerializer,
    SubscriptionLineInputSerializer,
    SubscriptionLineSerializer,
    SubscriptionSerializer,
    SubscriptionTransitionSerializer,
    SubscriptionUpdateSerializer,
    TaxRuleSerializer,
)


def parse_int(request, name: str):
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise DjangoValidationError({name: "Enter a whole number."})


def parse_bool(request, name: str):
    raw = request.query_params.get(name)
    if raw in (None, "", "false", "0", "False"):
        return False
    return raw.lower() in ("1", "true", "yes")


class PortalScopedMixin:
    """
    Portal users only ever see their own Customer's rows. Staff/admin see all.
    Filtering happens in the queryset — not the serializer — so an object the
    caller does not own is a 404, indistinguishable from "does not exist".
    """

    scope_field = "customer_id"

    def scoped(self, queryset):
        user = self.request.user
        if getattr(user, "customer_id", None):
            return queryset.filter(**{self.scope_field: user.customer_id})
        return queryset


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

class CustomerViewSet(PortalScopedMixin, viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [StaffWritePortalRead]
    scope_field = "id"

    def get_queryset(self):
        queryset = Customer.objects.annotate(
            subscription_count=Count("subscriptions", distinct=True)
        )
        queryset = self.scoped(queryset)
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(contact_email__icontains=search)
            )
        return queryset.order_by("name")


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]
    queryset = Product.objects.prefetch_related("variants")

    def get_queryset(self):
        queryset = super().get_queryset()
        if not parse_bool(self.request, "include_archived"):
            queryset = queryset.filter(active=True)
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset


class PlanViewSet(viewsets.ModelViewSet):
    serializer_class = PlanSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = Plan.objects.select_related("product")
        if not parse_bool(self.request, "include_archived"):
            queryset = queryset.filter(active=True)
        product_id = parse_int(self.request, "product")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        frequency = self.request.query_params.get("frequency")
        if frequency:
            queryset = queryset.filter(billing_frequency=frequency)
        if parse_bool(self.request, "selectable"):
            today = date.today()
            queryset = queryset.filter(
                active=True,
                availability_start__lte=today,
            ).filter(Q(availability_end__isnull=True) | Q(availability_end__gte=today))
        return queryset


class TaxRuleViewSet(viewsets.ModelViewSet):
    serializer_class = TaxRuleSerializer
    permission_classes = [IsStaffOrAdminReadAdminWrite]

    def get_queryset(self):
        queryset = TaxRule.objects.all()
        if not parse_bool(self.request, "include_archived"):
            queryset = queryset.filter(active=True)
        return queryset


class QuotationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationTemplateSerializer
    permission_classes = [IsAdminOrStaff]

    def get_queryset(self):
        queryset = QuotationTemplate.objects.select_related("plan").prefetch_related(
            "lines__product", "lines__variant"
        )
        plan_id = parse_int(self.request, "plan")
        if plan_id:
            queryset = queryset.filter(plan_id=plan_id)
        if not parse_bool(self.request, "include_archived"):
            queryset = queryset.filter(active=True)
        return queryset


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class SubscriptionViewSet(PortalScopedMixin, viewsets.ModelViewSet):
    permission_classes = [StaffWritePortalRead]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = (
            Subscription.objects.select_related("customer", "plan")
            .prefetch_related(
                "lines__product", "lines__variant", "lines__tax_rule"
            )
            .annotate(invoice_count=Count("invoices", distinct=True))
        )
        queryset = self.scoped(queryset)

        stage = self.request.query_params.get("stage")
        if stage:
            queryset = queryset.filter(stage=stage)
        customer_id = parse_int(self.request, "customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        plan_id = parse_int(self.request, "plan")
        if plan_id:
            queryset = queryset.filter(plan_id=plan_id)
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(
                Q(number__icontains=search) | Q(customer__name__icontains=search)
            )
        return queryset

    def get_serializer_class(self):
        return SubscriptionCreateSerializer if self.action == "create" else SubscriptionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription = serializer.save()
        return Response(
            SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        body = SubscriptionUpdateSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        if not body.validated_data:
            return Response(
                {"errors": {"detail": ["No editable fields supplied."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for field, value in body.validated_data.items():
            setattr(instance, field, value)
        instance.full_clean(exclude=["lines"])
        instance.save()
        return Response(SubscriptionSerializer(instance).data)

    # -- stage machine -------------------------------------------------
    def _transition(self, request, service, allowed: tuple[str, ...]):
        subscription = self.get_object()
        body = SubscriptionTransitionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        kwargs = {k: v for k, v in body.validated_data.items() if k in allowed}
        subscription = service(sub=subscription, actor=request.user, **kwargs)
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=["post"], url_path="send-quotation")
    def send_quotation(self, request, pk=None):
        return self._transition(request, subscription_services.send_quotation, ("on",))

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._transition(request, subscription_services.confirm, ("on",))

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self._transition(
            request, subscription_services.activate, ("start_date", "expiry_date")
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._transition(request, subscription_services.close, ("reason", "on"))

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        return self._transition(request, subscription_services.renew, ("on",))

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        subscription = self.get_object()
        subscription = subscription_services.set_paused(
            sub=subscription, actor=request.user, paused=True
        )
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        subscription = self.get_object()
        subscription = subscription_services.set_paused(
            sub=subscription, actor=request.user, paused=False
        )
        return Response(SubscriptionSerializer(subscription).data)

    # -- lines ----------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="lines")
    def add_line(self, request, pk=None):
        subscription = self.get_object()
        payload = SubscriptionLineInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        line = subscription_services.add_line(
            sub=subscription, actor=request.user, **payload.validated_data
        )
        return Response(
            SubscriptionLineSerializer(line).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["delete"], url_path=r"lines/(?P<line_id>[0-9]+)")
    def remove_line(self, request, pk=None, line_id=None):
        subscription = self.get_object()
        subscription_services.remove_line(
            sub=subscription, line_id=int(line_id), actor=request.user
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Invoices & payments
# ---------------------------------------------------------------------------

class InvoiceViewSet(PortalScopedMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [StaffWritePortalRead]

    def get_queryset(self):
        queryset = Invoice.objects.select_related("customer", "subscription")
        queryset = self.scoped(queryset)

        invoice_status = self.request.query_params.get("status")
        if invoice_status:
            queryset = queryset.filter(status=invoice_status)
        customer_id = parse_int(self.request, "customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        subscription_id = parse_int(self.request, "subscription")
        if subscription_id:
            queryset = queryset.filter(subscription_id=subscription_id)
        if parse_bool(self.request, "overdue"):
            queryset = queryset.filter(
                status=Invoice.Status.CONFIRMED, due_date__lt=date.today()
            )
        if parse_bool(self.request, "unpaid"):
            queryset = queryset.filter(status=Invoice.Status.CONFIRMED)
        return queryset

    def get_serializer_class(self):
        return InvoiceListSerializer if self.action == "list" else InvoiceSerializer

    def get_queryset_for_detail(self):
        return self.get_queryset().prefetch_related(
            "lines", "payments", "applied_discounts__rule"
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance = self.get_queryset_for_detail().get(pk=instance.pk)
        return Response(InvoiceSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        invoice = billing_services.confirm_invoice(invoice=self.get_object(), actor=request.user)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        invoice = billing_services.send_invoice(invoice=self.get_object(), actor=request.user)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="mark-printed")
    def mark_printed(self, request, pk=None):
        invoice = billing_services.mark_printed(invoice=self.get_object(), actor=request.user)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invoice = billing_services.cancel_invoice(
            invoice=self.get_object(), actor=request.user,
            reason=request.data.get("reason", ""),
        )
        return Response(InvoiceSerializer(invoice).data)


class PaymentViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin,
    mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet,
):
    permission_classes = [IsAdminOrStaff]

    def get_queryset(self):
        queryset = Payment.objects.select_related("invoice", "recorded_by")
        invoice_id = parse_int(self.request, "invoice")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)
        customer_id = parse_int(self.request, "customer")
        if customer_id:
            queryset = queryset.filter(invoice__customer_id=customer_id)
        return queryset

    def get_serializer_class(self):
        return PaymentCreateSerializer if self.action == "create" else PaymentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(
            PaymentSerializer(payment).data, status=status.HTTP_201_CREATED
        )

    def perform_destroy(self, instance):
        payment_services.remove_payment(payment=instance, actor=self.request.user)


# ---------------------------------------------------------------------------
# Discounts & billing runs
# ---------------------------------------------------------------------------

class DiscountRuleViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin,
    mixins.CreateModelMixin, viewsets.GenericViewSet,
):
    """Rules are never deleted: deactivating keeps invoice history truthful."""

    permission_classes = [IsAdminOnly]

    def get_queryset(self):
        queryset = DiscountRule.objects.prefetch_related("products", "subscriptions")
        if parse_bool(self.request, "active_only"):
            queryset = queryset.filter(active=True)
        return queryset

    def get_serializer_class(self):
        return DiscountRuleCreateSerializer if self.action == "create" else DiscountRuleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = serializer.save()
        return Response(DiscountRuleSerializer(rule).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        rule = billing_services.deactivate_discount_rule(
            rule=self.get_object(), actor=request.user
        )
        return Response(DiscountRuleSerializer(rule).data)


class BillingRunViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminOrStaff]
    serializer_class = BillingRunSerializer

    def get_queryset(self):
        return BillingRun.objects.annotate(invoice_count=Count("invoices"))

    @action(detail=False, methods=["post"])
    def run(self, request):
        """
        Execute the billing day. ``dry_run: true`` answers "what would be
        billed" without writing — the safe call for an agent to make first.
        """
        body = BillingRunRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        on = body.validated_data.get("on") or date.today()
        if body.validated_data["dry_run"]:
            return Response(billing_services.preview_billing_day(on=on))
        run = billing_services.run_billing_day(on=on, actor=request.user)
        return Response(BillingRunSerializer(run).data, status=status.HTTP_201_CREATED)
