"""
One error shape for the whole API.

Domain code raises ``django.core.exceptions.ValidationError`` (models,
services), ``PermissionDenied`` (role gates) and ``InvalidTransition`` (stage
machine). DRF raises its own exceptions. Clients must never have to guess
which dialect answered, so everything is normalised to::

    {"errors": {"field": ["message", ...]}, "code": "optional_machine_code"}

``errors`` is a dict for field errors, or a list for non-field problems.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _normalise(detail):
    """Turn DRF's ErrorDetail trees into plain JSON-safe structures."""
    if isinstance(detail, dict):
        return {str(key): _normalise(value) for key, value in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_normalise(item) for item in detail]
    return str(detail)


def _django_field_errors(exc: DjangoValidationError) -> dict:
    if hasattr(exc, "message_dict"):
        return {
            key: [str(message) for message in (value if isinstance(value, (list, tuple)) else [value])]
            for key, value in exc.message_dict.items()
        }
    return {"non_field_errors": [str(message) for message in exc.messages]}


def api_exception_handler(exc, context):
    """
    Normalise domain + DRF errors. Returning ``None`` lets Django answer with a
    500, so genuinely unexpected failures still surface loudly in logs.
    """
    # Imported lazily: this module is loaded while settings are configured.
    from apps.subscriptions.models import InvalidTransition

    if isinstance(exc, DjangoValidationError):
        return Response(
            {"errors": _django_field_errors(exc)}, status=status.HTTP_400_BAD_REQUEST
        )

    if isinstance(exc, InvalidTransition):
        return Response(
            {"errors": {"stage": [exc.reason]}, "code": "invalid_transition"},
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, (ObjectDoesNotExist, Http404)):
        return Response(
            {"errors": {"detail": ["Not found."]}}, status=status.HTTP_404_NOT_FOUND
        )

    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            {"errors": {"detail": [str(exc) or "Permission denied."]}},
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, IntegrityError):
        # Two writers raced on a unique index / check constraint. The caller can
        # retry safely because domain invariants held for whoever won.
        return Response(
            {"errors": {"detail": ["Conflicting write; the record changed underneath you."]},
             "code": "conflict"},
            status=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    response.data = {"errors": _normalise(response.data)}
    return response
