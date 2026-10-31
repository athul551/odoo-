"""Shared DRF permissions driven by the domain Role, not Django flags."""

from rest_framework.permissions import SAFE_METHODS, BasePermission


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


class IsAdminOrReadOnly(BasePermission):
    """
    Catalog-shaped data: everyone signed in may read it (the portal must show
    the plans it can buy), only Admins may change it (CONTEXT.md: "Only role
    that can create Plans, Taxes, Discount Rules, and other Users").
    """

    message = "Admin access required to change this resource."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.is_admin)


class StaffWritePortalRead(BasePermission):
    """
    Sales/billing records: the portal reads (its own rows only, enforced by
    queryset scoping) but every write belongs to staff or admin.
    """

    message = "Only admin or staff may change this resource."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.is_member_of_staff)


class IsStaffOrAdminReadAdminWrite(BasePermission):
    """Configuration staff may inspect (taxes, templates) but only Admins change."""

    message = "Admin access required to change this resource."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_member_of_staff):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.is_admin)


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
