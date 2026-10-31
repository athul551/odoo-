"""Shared DRF permissions driven by the domain Role, not Django flags."""

from rest_framework.permissions import BasePermission


class IsAdminOrStaff(BasePermission):
    """Internal operators only — the finance views never face the portal."""

    message = "Admin or staff access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_member_of_staff)


class IsAdminOnly(BasePermission):
    """Discount rules, staff management, tax rules — admin territory (spec)."""

    message = "Admin access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin)


class IsPortalCustomer(BasePermission):
    """Customer users may only ever see rows scoped to their own Customer."""

    message = "Customer access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.customer_id is not None
        )

    def has_object_permission(self, request, view, obj):
        customer_id = request.user.customer_id
        if getattr(obj, "customer_id", None) == customer_id:
            return True
        subscription = getattr(obj, "subscription", None)
        return subscription is not None and subscription.customer_id == customer_id
