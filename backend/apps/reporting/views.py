from datetime import date

from django.core.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrStaff

from . import services

MAX_PAGE_SIZE = 200


def _parse_date(request, name: str) -> date | None:
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationError({name: "Use ISO format YYYY-MM-DD."})


def _parse_int(request, name: str, *, default=None, minimum=None, maximum=None):
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError({name: "Enter a whole number."})
    if minimum is not None and value < minimum:
        raise ValidationError({name: f"Must be at least {minimum}."})
    if maximum is not None and value > maximum:
        raise ValidationError({name: f"Must be at most {maximum}."})
    return value


class SummaryView(APIView):
    """One place: active subs, MRR/ARR, invoiced, collected, outstanding, overdue."""

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        try:
            data = services.summary(
                start=_parse_date(request, "start"),
                end=_parse_date(request, "end"),
                on=_parse_date(request, "as_of"),
                customer_id=_parse_int(request, "customer_id", minimum=1),
            )
        except ValidationError as exc:
            return Response({"errors": exc.message_dict if hasattr(exc, "message_dict")
                             else [str(exc)]}, status=400)
        return Response(data)


class ExpiringListView(APIView):
    """Subscriptions whose term ends inside the next N days — the renewal queue."""

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        try:
            within_days = _parse_int(request, "within_days", default=30, minimum=1,
                                     maximum=365)
            customer_id = _parse_int(request, "customer_id", minimum=1)
            on = _parse_date(request, "as_of")
            page = _parse_int(request, "page", default=1, minimum=1)
            page_size = min(_parse_int(request, "page_size", default=50, minimum=1) or 50,
                            MAX_PAGE_SIZE)
        except ValidationError as exc:
            return Response({"errors": exc.message_dict if hasattr(exc, "message_dict")
                             else [str(exc)]}, status=400)

        qs = services.expiring_qs(within_days=within_days, customer_id=customer_id, on=on)
        total = qs.count()
        start_at = (page - 1) * page_size
        rows = list(qs[start_at:start_at + page_size])
        return Response({
            "within_days": within_days,
            "page": page,
            "page_size": page_size,
            "total": total,
            "results": [
                {
                    "number": sub.number,
                    "id": sub.pk,
                    "customer": sub.customer.name,
                    "plan": sub.plan.name,
                    "expiry_date": sub.expiry_date.isoformat(),
                    "allow_renew": bool(sub.plan.allow_renew),
                    "total": str(sub.total),
                }
                for sub in rows
            ],
        })


class ChaseListView(APIView):
    """Paginated outstanding/overdue invoice lists for the collections chase."""

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        kind = request.query_params.get("kind", "overdue")
        if kind not in ("overdue", "outstanding"):
            return Response({"errors": {"kind": "Use 'overdue' or 'outstanding'."}}, status=400)
        try:
            qs = services.chase_qs(
                kind=kind,
                on=_parse_date(request, "as_of"),
                customer_id=_parse_int(request, "customer_id", minimum=1),
                older_than_days=_parse_int(request, "older_than_days", minimum=0),
            )
            page = _parse_int(request, "page", default=1, minimum=1)
            page_size = min(_parse_int(request, "page_size", default=50, minimum=1) or 50,
                            MAX_PAGE_SIZE)
        except ValidationError as exc:
            return Response({"errors": exc.message_dict if hasattr(exc, "message_dict")
                             else [str(exc)]}, status=400)

        total = qs.count()
        start_at = (page - 1) * page_size
        rows = list(qs[start_at:start_at + page_size])
        return Response({
            "kind": kind,
            "page": page,
            "page_size": page_size,
            "total": total,
            "results": [
                {
                    "number": inv.number,
                    "customer": inv.customer.name,
                    "subscription": inv.subscription.number,
                    "period": [inv.period_start.isoformat(), inv.period_end.isoformat()],
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                    "total": str(inv.total),
                    "amount_paid": str(inv.amount_paid),
                    "amount_due": str(inv.amount_due),
                }
                for inv in rows
            ],
        })
