"""
The tool catalogue. Each tool is a thin, typed door onto a domain service:

* reads return the same shapes the REST API returns (shared serializers),
* writes call the same services the API calls, so role gates, stage rules and
  ledger maths are enforced identically no matter which agent is driving.

Naming is deliberately verb-first and domain-specific so a model can pick the
right tool from the description alone.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from apps.accounts.serializers import UserSerializer
from apps.api.serializers import (
    BillingRunSerializer,
    CustomerSerializer,
    DiscountRuleSerializer,
    InvoiceListSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    PlanSerializer,
    ProductSerializer,
    SubscriptionSerializer,
    TaxRuleSerializer,
)
from apps.billing import services as billing_services
from apps.billing.models import BillingRun, DiscountRule, Invoice
from apps.customers.models import Customer
from apps.payments import services as payment_services
from apps.payments.models import Payment
from apps.products.models import Plan, Product
from apps.quotations.models import QuotationTemplate
from apps.reporting import services as reporting_services
from apps.subscriptions import services as subscription_services
from apps.subscriptions.models import Subscription

from .protocol import ServerContext, Tool

MAX_LIMIT = 200


class ToolInputError(Exception):
    """Bad arguments; surfaced to the agent as a tool error, not a crash."""


# ---------------------------------------------------------------------------
# argument helpers
# ---------------------------------------------------------------------------

def _schema(properties: dict, required: tuple[str, ...] = ()) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _int(args: dict, key: str, *, default=None, minimum=None, maximum=None):
    raw = args.get(key, default)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ToolInputError(f"{key} must be a whole number.")
    if minimum is not None and value < minimum:
        raise ToolInputError(f"{key} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise ToolInputError(f"{key} must be at most {maximum}.")
    return value


def _date(args: dict, key: str):
    raw = args.get(key)
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ToolInputError(f"{key} must be an ISO date (YYYY-MM-DD).")


def _bool(args: dict, key: str, *, default: bool = False) -> bool:
    raw = args.get(key, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _decimal(args: dict, key: str):
    raw = args.get(key)
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise ToolInputError(f"{key} must be a decimal number.")


def _limit(args: dict, default: int = 20) -> int:
    return min(_int(args, "limit", default=default, minimum=1) or default, MAX_LIMIT)


def _one(queryset, label: str, reference):
    try:
        return queryset.get(**reference)
    except ObjectDoesNotExist:
        raise ToolInputError(f"No {label} matched {reference}.")
    except Exception:  # MultipleObjectsReturned etc.
        raise ToolInputError(f"{label} reference is ambiguous: {reference}.")


def _subscription(reference) -> Subscription:
    if reference in (None, ""):
        raise ToolInputError("subscription (number or id) is required.")
    queryset = Subscription.objects.select_related("customer", "plan").prefetch_related(
        "lines__product", "lines__variant", "lines__tax_rule"
    )
    text = str(reference).strip()
    if text.isdigit():
        return _one(queryset, "subscription", {"pk": int(text)})
    return _one(queryset, "subscription", {"number": text})


def _invoice(reference) -> Invoice:
    if reference in (None, ""):
        raise ToolInputError("invoice (number or id) is required.")
    queryset = Invoice.objects.select_related("customer", "subscription").prefetch_related(
        "lines", "payments", "applied_discounts__rule"
    )
    text = str(reference).strip()
    if text.isdigit():
        return _one(queryset, "invoice", {"pk": int(text)})
    return _one(queryset, "invoice", {"number": text})


def _payment(reference) -> Payment:
    payment_id = _int({"payment_id": reference}, "payment_id", minimum=1)
    return _one(Payment.objects.select_related("invoice"), "payment", {"pk": payment_id})


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, schema: dict, *, write: bool = False):
    def register(handler):
        TOOLS[name] = Tool(
            name=name, description=description, input_schema=schema,
            handler=handler, write=write,
        )
        return handler
    return register


# ---------------------------------------------------------------------------
# identity & context
# ---------------------------------------------------------------------------

@tool("whoami", "Show which Brightloop user this MCP server acts as, and its role.",
      _schema({}))
def whoami(args: dict, ctx: ServerContext):
    data = UserSerializer(ctx.actor).data
    data["read_only"] = ctx.read_only
    data["capabilities"] = {
        "can_write": not ctx.read_only,
        "can_admin": bool(ctx.actor.is_admin),
    }
    return data


@tool("list_customers", "List customer organizations, optionally filtered by name or email.",
      _schema({"q": {"type": "string"}, "limit": {"type": "integer", "minimum": 1}}))
def list_customers(args: dict, ctx: ServerContext):
    queryset = Customer.objects.order_by("name")
    search = args.get("q")
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(contact_email__icontains=search)
        )
    rows = list(queryset[: _limit(args)])
    return {"count": queryset.count(), "results": CustomerSerializer(rows, many=True).data}


@tool("get_customer", "Read one customer organization by id.",
      _schema({"customer_id": {"type": "integer"}}, ("customer_id",)))
def get_customer(args: dict, ctx: ServerContext):
    customer = _one(Customer.objects.all(), "customer",
                    {"pk": _int(args, "customer_id", minimum=1)})
    return CustomerSerializer(customer).data


@tool("list_products", "List the catalog (products and their variants).",
      _schema({"q": {"type": "string"}, "limit": {"type": "integer", "minimum": 1}}))
def list_products(args: dict, ctx: ServerContext):
    queryset = Product.objects.prefetch_related("variants").filter(active=True)
    if args.get("q"):
        queryset = queryset.filter(name__icontains=args["q"])
    rows = list(queryset[: _limit(args)])
    return {"count": queryset.count(), "results": ProductSerializer(rows, many=True).data}


@tool(
    "list_plans",
    "List subscription plans with price, frequency and availability. Use "
    "selectable_only=true to see only plans a new subscription may use today.",
    _schema({
        "product_id": {"type": "integer"},
        "frequency": {"type": "string", "enum": ["daily", "weekly", "monthly", "yearly"]},
        "selectable_only": {"type": "boolean"},
        "limit": {"type": "integer", "minimum": 1},
    }),
)
def list_plans(args: dict, ctx: ServerContext):
    queryset = Plan.objects.select_related("product").filter(active=True)
    product_id = _int(args, "product_id", minimum=1)
    if product_id:
        queryset = queryset.filter(product_id=product_id)
    if args.get("frequency"):
        queryset = queryset.filter(billing_frequency=args["frequency"])
    if _bool(args, "selectable_only"):
        today = date.today()
        queryset = queryset.filter(availability_start__lte=today).filter(
            Q(availability_end__isnull=True) | Q(availability_end__gte=today)
        )
    rows = list(queryset[: _limit(args)])
    return {"count": queryset.count(), "results": PlanSerializer(rows, many=True).data}


@tool("list_tax_rules", "List tax rules (name and percentage rate).",
      _schema({"limit": {"type": "integer", "minimum": 1}}))
def list_tax_rules(args: dict, ctx: ServerContext):
    from apps.billing.models import TaxRule

    queryset = TaxRule.objects.filter(active=True)
    rows = list(queryset[: _limit(args)])
    return {"count": queryset.count(), "results": TaxRuleSerializer(rows, many=True).data}


# ---------------------------------------------------------------------------
# subscriptions
# ---------------------------------------------------------------------------

@tool(
    "list_subscriptions",
    "List subscriptions. Filter by customer, stage (draft/quotation/confirmed/"
    "active/closed) or free-text number/customer name.",
    _schema({
        "customer_id": {"type": "integer"},
        "stage": {"type": "string",
                  "enum": ["draft", "quotation", "confirmed", "active", "closed"]},
        "q": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1},
    }),
)
def list_subscriptions(args: dict, ctx: ServerContext):
    queryset = (
        Subscription.objects.select_related("customer", "plan")
        .prefetch_related("lines__product", "lines__variant", "lines__tax_rule")
    )
    customer_id = _int(args, "customer_id", minimum=1)
    if customer_id:
        queryset = queryset.filter(customer_id=customer_id)
    if args.get("stage"):
        queryset = queryset.filter(stage=args["stage"])
    if args.get("q"):
        queryset = queryset.filter(
            Q(number__icontains=args["q"]) | Q(customer__name__icontains=args["q"])
        )
    rows = list(queryset[: _limit(args)])
    return {
        "count": queryset.count(),
        "results": SubscriptionSerializer(rows, many=True).data,
    }


@tool("get_subscription", "Read one subscription (lines, totals, stage) by number or id.",
      _schema({"subscription": {"type": "string"}}, ("subscription",)))
def get_subscription(args: dict, ctx: ServerContext):
    return SubscriptionSerializer(_subscription(args.get("subscription"))).data


@tool(
    "create_subscription",
    "Create a Draft subscription for a customer on a plan, optionally with "
    "lines. The plan must be selectable today. Returns the new SUB- number.",
    _schema({
        "customer_id": {"type": "integer"},
        "plan_id": {"type": "integer"},
        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
        "expiry_date": {"type": "string", "description": "YYYY-MM-DD; defaults to one period"},
        "payment_terms_days": {"type": "integer", "minimum": 0, "maximum": 365},
        "template_id": {"type": "integer"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "variant_id": {"type": "integer"},
                    "quantity": {"type": "integer", "minimum": 1},
                    "tax_rule_id": {"type": "integer"},
                    "unit_price": {"type": "string"},
                },
                "required": ["product_id"],
            },
        },
    }, ("customer_id", "plan_id", "start_date")),
    write=True,
)
def create_subscription(args: dict, ctx: ServerContext):
    customer = _one(Customer.objects.all(), "customer",
                    {"pk": _int(args, "customer_id", minimum=1)})
    plan = _one(Plan.objects.select_related("product"), "plan",
                {"pk": _int(args, "plan_id", minimum=1)})
    template = None
    if args.get("template_id"):
        template = _one(QuotationTemplate.objects.all(), "quotation template",
                        {"pk": _int(args, "template_id", minimum=1)})
    subscription = subscription_services.create_subscription(
        customer=customer,
        plan=plan,
        start_date=_date(args, "start_date"),
        expiry_date=_date(args, "expiry_date"),
        payment_terms_days=_int(args, "payment_terms_days", default=30),
        actor=ctx.actor,
        origin_template=template,
    )
    for line in args.get("lines") or []:
        if not isinstance(line, dict):
            raise ToolInputError("Each line must be an object.")
        product = _one(Product.objects.all(), "product",
                       {"pk": _int(line, "product_id", minimum=1)})
        from apps.products.models import ProductVariant

        variant = None
        if line.get("variant_id"):
            variant = _one(ProductVariant.objects.all(), "variant",
                           {"pk": _int(line, "variant_id", minimum=1)})
        from apps.billing.models import TaxRule

        tax_rule = None
        if line.get("tax_rule_id"):
            tax_rule = _one(TaxRule.objects.all(), "tax rule",
                            {"pk": _int(line, "tax_rule_id", minimum=1)})
        subscription_services.add_line(
            sub=subscription, actor=ctx.actor, product=product,
            quantity=_int(line, "quantity", default=1, minimum=1),
            variant=variant, tax_rule=tax_rule,
            unit_price=_decimal(line, "unit_price"),
        )
    return SubscriptionSerializer(_subscription(subscription.pk)).data


@tool(
    "add_subscription_line",
    "Add a product line to a Draft/Quotation subscription. Quantity must meet "
    "the plan minimum; (product, variant) may appear only once.",
    _schema({
        "subscription": {"type": "string"},
        "product_id": {"type": "integer"},
        "quantity": {"type": "integer", "minimum": 1},
        "variant_id": {"type": "integer"},
        "tax_rule_id": {"type": "integer"},
        "unit_price": {"type": "string"},
    }, ("subscription", "product_id")),
    write=True,
)
def add_subscription_line(args: dict, ctx: ServerContext):
    subscription = _subscription(args.get("subscription"))
    product = _one(Product.objects.all(), "product",
                   {"pk": _int(args, "product_id", minimum=1)})
    from apps.billing.models import TaxRule
    from apps.products.models import ProductVariant

    variant = None
    if args.get("variant_id"):
        variant = _one(ProductVariant.objects.all(), "variant",
                       {"pk": _int(args, "variant_id", minimum=1)})
    tax_rule = None
    if args.get("tax_rule_id"):
        tax_rule = _one(TaxRule.objects.all(), "tax rule",
                        {"pk": _int(args, "tax_rule_id", minimum=1)})
    subscription_services.add_line(
        sub=subscription, actor=ctx.actor, product=product,
        quantity=_int(args, "quantity", default=1, minimum=1),
        variant=variant, tax_rule=tax_rule, unit_price=_decimal(args, "unit_price"),
    )
    return SubscriptionSerializer(_subscription(subscription.pk)).data


@tool(
    "remove_subscription_line",
    "Remove a line from a Draft/Quotation subscription and recompute totals.",
    _schema({"subscription": {"type": "string"},
             "line_id": {"type": "integer"}}, ("subscription", "line_id")),
    write=True,
)
def remove_subscription_line(args: dict, ctx: ServerContext):
    subscription = _subscription(args.get("subscription"))
    subscription_services.remove_line(
        sub=subscription, line_id=_int(args, "line_id", minimum=1), actor=ctx.actor
    )
    return SubscriptionSerializer(_subscription(subscription.pk)).data


TRANSITIONS = {
    "send_quotation": "Draft -> Quotation (requires at least one line)",
    "confirm": "Quotation -> Confirmed (refuses lapsed validity / closed plans)",
    "activate": "Confirmed -> Active (optionally override start/expiry dates)",
    "close": "any open stage -> Closed (early close may be refused by the plan)",
    "renew": "extend an Active term by one period, or reopen an expired Closed term",
    "pause": "pause billing on an Active subscription",
    "resume": "resume billing on an Active subscription",
}


@tool(
    "subscription_transition",
    "Move a subscription through its stage machine or pause/resume it. Legal "
    "moves only: " + "; ".join(f"{k}: {v}" for k, v in TRANSITIONS.items()),
    _schema({
        "subscription": {"type": "string"},
        "action": {"type": "string", "enum": sorted(TRANSITIONS)},
        "on": {"type": "string", "description": "YYYY-MM-DD business date, defaults to today"},
        "start_date": {"type": "string"},
        "expiry_date": {"type": "string"},
        "reason": {"type": "string", "description": "required reading for close"},
    }, ("subscription", "action")),
    write=True,
)
def subscription_transition(args: dict, ctx: ServerContext):
    subscription = _subscription(args.get("subscription"))
    action = args.get("action")
    actor = ctx.actor
    on = _date(args, "on")

    if action == "send_quotation":
        subscription = subscription_services.send_quotation(
            sub=subscription, actor=actor, on=on
        )
    elif action == "confirm":
        subscription = subscription_services.confirm(sub=subscription, actor=actor, on=on)
    elif action == "activate":
        subscription = subscription_services.activate(
            sub=subscription, actor=actor,
            start_date=_date(args, "start_date"), expiry_date=_date(args, "expiry_date"),
        )
    elif action == "close":
        subscription = subscription_services.close(
            sub=subscription, actor=actor,
            reason=args.get("reason") or "Closed by operator", on=on,
        )
    elif action == "renew":
        subscription = subscription_services.renew(sub=subscription, actor=actor, on=on)
    elif action == "pause":
        subscription = subscription_services.set_paused(
            sub=subscription, actor=actor, paused=True
        )
    elif action == "resume":
        subscription = subscription_services.set_paused(
            sub=subscription, actor=actor, paused=False
        )
    else:
        raise ToolInputError(f"action must be one of {sorted(TRANSITIONS)}")

    return SubscriptionSerializer(_subscription(subscription.pk)).data


# ---------------------------------------------------------------------------
# billing
# ---------------------------------------------------------------------------

def _billing_preview(on: date | None):
    return billing_services.preview_billing_day(on=on)


@tool(
    "preview_billing_day",
    "Read-only: which subscription periods would be billed on a given date. "
    "Nothing is written; run this before run_billing_day.",
    _schema({"on": {"type": "string", "description": "YYYY-MM-DD, defaults to today"}}),
)
def preview_billing_day(args: dict, ctx: ServerContext):
    return _billing_preview(_date(args, "on"))


@tool(
    "run_billing_day",
    "Execute the billing batch. Idempotent: a period already invoiced is "
    "skipped. Requires confirm=true; without it you get the preview back.",
    _schema({
        "on": {"type": "string"},
        "confirm": {"type": "boolean"},
    }),
    write=True,
)
def run_billing_day(args: dict, ctx: ServerContext):
    on = _date(args, "on")
    if not _bool(args, "confirm"):
        return {"executed": False, "preview": _billing_preview(on)}
    run = billing_services.run_billing_day(on=on, actor=ctx.actor)
    return {"executed": True, **BillingRunSerializer(run).data}


@tool(
    "list_invoices",
    "List invoices. Filter by customer, status (draft/confirmed/paid/cancelled), "
    "subscription id, or overdue=true.",
    _schema({
        "customer_id": {"type": "integer"},
        "status": {"type": "string",
                   "enum": ["draft", "confirmed", "paid", "cancelled"]},
        "subscription_id": {"type": "integer"},
        "overdue": {"type": "boolean"},
        "limit": {"type": "integer", "minimum": 1},
    }),
)
def list_invoices(args: dict, ctx: ServerContext):
    queryset = Invoice.objects.select_related("customer", "subscription")
    customer_id = _int(args, "customer_id", minimum=1)
    if customer_id:
        queryset = queryset.filter(customer_id=customer_id)
    if args.get("status"):
        queryset = queryset.filter(status=args["status"])
    subscription_id = _int(args, "subscription_id", minimum=1)
    if subscription_id:
        queryset = queryset.filter(subscription_id=subscription_id)
    if _bool(args, "overdue"):
        queryset = queryset.filter(
            status=Invoice.Status.CONFIRMED, due_date__lt=date.today()
        )
    rows = list(queryset[: _limit(args)])
    return {
        "count": queryset.count(),
        "results": InvoiceListSerializer(rows, many=True).data,
    }


@tool("get_invoice", "Read one invoice with its lines, payments and discounts.",
      _schema({"invoice": {"type": "string"}}, ("invoice",)))
def get_invoice(args: dict, ctx: ServerContext):
    return InvoiceSerializer(_invoice(args.get("invoice"))).data


INVOICE_ACTIONS = ("confirm", "send", "print", "cancel")


@tool(
    "invoice_action",
    "Advance or cancel an invoice: confirm (issues it and sets the due date), "
    "send, print, or cancel (cancelling with payments attached is refused — "
    "remove the payments first).",
    _schema({
        "invoice": {"type": "string"},
        "action": {"type": "string", "enum": list(INVOICE_ACTIONS)},
        "reason": {"type": "string"},
    }, ("invoice", "action")),
    write=True,
)
def invoice_action(args: dict, ctx: ServerContext):
    invoice = _invoice(args.get("invoice"))
    action = args.get("action")
    if action == "confirm":
        invoice = billing_services.confirm_invoice(invoice=invoice, actor=ctx.actor)
    elif action == "send":
        invoice = billing_services.send_invoice(invoice=invoice, actor=ctx.actor)
    elif action == "print":
        invoice = billing_services.mark_printed(invoice=invoice, actor=ctx.actor)
    elif action == "cancel":
        invoice = billing_services.cancel_invoice(
            invoice=invoice, actor=ctx.actor, reason=args.get("reason", "")
        )
    else:
        raise ToolInputError(f"action must be one of {INVOICE_ACTIONS}")
    return InvoiceSerializer(_invoice(invoice.pk)).data


@tool(
    "record_payment",
    "Record money against a confirmed invoice. Overpayment is refused; the "
    "invoice becomes Paid once the ledger covers its total.",
    _schema({
        "invoice": {"type": "string"},
        "amount": {"type": "string"},
        "method": {"type": "string",
                   "enum": ["bank_transfer", "card", "cash", "check", "other"]},
        "paid_on": {"type": "string", "description": "YYYY-MM-DD, defaults to today"},
        "reference": {"type": "string"},
        "note": {"type": "string"},
    }, ("invoice", "amount", "method")),
    write=True,
)
def record_payment(args: dict, ctx: ServerContext):
    invoice = _invoice(args.get("invoice"))
    amount = _decimal(args, "amount")
    if amount is None:
        raise ToolInputError("amount is required.")
    payment = payment_services.record_payment(
        invoice=invoice, actor=ctx.actor, amount=amount, method=args.get("method"),
        paid_on=_date(args, "paid_on"),
        reference=args.get("reference", ""), note=args.get("note", ""),
    )
    return {
        "payment": PaymentSerializer(payment).data,
        "invoice": InvoiceSerializer(_invoice(invoice.pk)).data,
    }


@tool(
    "remove_payment",
    "Delete a mis-recorded payment; the invoice re-derives its status from the "
    "remaining ledger (Paid drops back to Confirmed).",
    _schema({"payment_id": {"type": "integer"}}, ("payment_id",)),
    write=True,
)
def remove_payment(args: dict, ctx: ServerContext):
    payment = _payment(args.get("payment_id"))
    invoice_id = payment.invoice_id
    payment_services.remove_payment(payment=payment, actor=ctx.actor)
    return InvoiceSerializer(_invoice(invoice_id)).data


# ---------------------------------------------------------------------------
# discounts & reporting
# ---------------------------------------------------------------------------

@tool("list_discount_rules", "List discount rules with their usage count.",
      _schema({"active_only": {"type": "boolean"},
               "limit": {"type": "integer", "minimum": 1}}))
def list_discount_rules(args: dict, ctx: ServerContext):
    queryset = DiscountRule.objects.prefetch_related("products", "subscriptions")
    if _bool(args, "active_only"):
        queryset = queryset.filter(active=True)
    rows = list(queryset[: _limit(args)])
    return {
        "count": queryset.count(),
        "results": DiscountRuleSerializer(rows, many=True).data,
    }


@tool(
    "create_discount_rule",
    "Admin only. Create an automatic discount: percent/fixed, product- or "
    "subscription-scoped, with an optional window, minimums and usage limit.",
    _schema({
        "name": {"type": "string"},
        "scope": {"type": "string", "enum": ["product", "subscription"]},
        "kind": {"type": "string", "enum": ["percent", "amount"]},
        "value": {"type": "string"},
        "applies_from": {"type": "string"},
        "applies_until": {"type": "string"},
        "minimum_amount": {"type": "string"},
        "minimum_quantity": {"type": "integer", "minimum": 1},
        "usage_limit": {"type": "integer", "minimum": 1},
        "product_ids": {"type": "array", "items": {"type": "integer"}},
        "subscription_ids": {"type": "array", "items": {"type": "integer"}},
    }, ("name", "scope", "kind", "value", "applies_from")),
    write=True,
)
def create_discount_rule(args: dict, ctx: ServerContext):
    rule = billing_services.create_discount_rule(
        actor=ctx.actor,
        name=args.get("name"),
        kind=args.get("kind"),
        value=_decimal(args, "value"),
        scope=args.get("scope"),
        applies_from=_date(args, "applies_from"),
        applies_until=_date(args, "applies_until"),
        minimum_amount=_decimal(args, "minimum_amount"),
        minimum_quantity=_int(args, "minimum_quantity", minimum=1),
        usage_limit=_int(args, "usage_limit", minimum=1),
        product_ids=args.get("product_ids") or (),
        subscription_ids=args.get("subscription_ids") or (),
    )
    return DiscountRuleSerializer(rule).data


@tool(
    "deactivate_discount_rule",
    "Admin only. Retire a rule without touching invoices already issued.",
    _schema({"rule_id": {"type": "integer"}}, ("rule_id",)),
    write=True,
)
def deactivate_discount_rule(args: dict, ctx: ServerContext):
    rule = _one(DiscountRule.objects.all(), "discount rule",
                {"pk": _int(args, "rule_id", minimum=1)})
    rule = billing_services.deactivate_discount_rule(rule=rule, actor=ctx.actor)
    return DiscountRuleSerializer(rule).data


@tool(
    "reporting_summary",
    "Month-end picture: active/paused subscriptions, MRR, ARR, invoiced, "
    "collected, outstanding and overdue — over the billed window.",
    _schema({
        "start": {"type": "string", "description": "YYYY-MM-DD"},
        "end": {"type": "string"},
        "as_of": {"type": "string"},
        "customer_id": {"type": "integer"},
    }),
)
def reporting_summary(args: dict, ctx: ServerContext):
    return reporting_services.summary(
        start=_date(args, "start"),
        end=_date(args, "end"),
        on=_date(args, "as_of"),
        customer_id=_int(args, "customer_id", minimum=1),
    )


@tool(
    "reporting_chase",
    "Collections lists: overdue invoices (optionally older_than_days) or "
    "outstanding ones not yet due, oldest due first.",
    _schema({
        "kind": {"type": "string", "enum": ["overdue", "outstanding"]},
        "as_of": {"type": "string"},
        "older_than_days": {"type": "integer", "minimum": 0},
        "customer_id": {"type": "integer"},
        "limit": {"type": "integer", "minimum": 1},
    }, ("kind",)),
)
def reporting_chase(args: dict, ctx: ServerContext):
    kind = args.get("kind")
    if kind not in ("overdue", "outstanding"):
        raise ToolInputError("kind must be 'overdue' or 'outstanding'.")
    queryset = reporting_services.chase_qs(
        kind=kind,
        on=_date(args, "as_of"),
        customer_id=_int(args, "customer_id", minimum=1),
        older_than_days=_int(args, "older_than_days", minimum=0),
    )
    rows = list(queryset[: _limit(args)])
    results = [
        {
            "number": inv.number,
            "customer": inv.customer.name,
            "subscription": inv.subscription.number,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "total": str(inv.total),
            "amount_due": str(inv.amount_due),
        }
        for inv in rows
    ]
    return {"kind": kind, "count": queryset.count(), "results": results}


@tool("list_billing_runs", "Recent billing batches with billed/skipped counts.",
      _schema({"limit": {"type": "integer", "minimum": 1}}))
def list_billing_runs(args: dict, ctx: ServerContext):
    queryset = BillingRun.objects.all()
    rows = list(queryset[: _limit(args, default=10)])
    return {
        "count": queryset.count(),
        "results": BillingRunSerializer(rows, many=True).data,
    }


def build_tools() -> dict[str, Tool]:
    return dict(TOOLS)
