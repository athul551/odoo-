from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    """
    Authentication identity for Brightloop. Logs in with email + password.

    Domain rules (CONTEXT.md / ADR 0003):
    - email is the unique, global identity across admin/staff/customer roles
    - every user has exactly one role
    - only customer-role users belong to a Customer; staff/admin never do
    - only Admins may create staff/admin users (enforced at the service layer)
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        STAFF = "staff", "Staff"
        CUSTOMER = "customer", "Customer"

    username = None
    email = models.EmailField(unique=True, verbose_name="email address")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    # Which Customer this user acts for. Must be null unless role == CUSTOMER.
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        constraints = [
            # Case-insensitive global email identity (ADR 0003): nobody can take
            # Admin@shire.io once admin@shire.io exists, even via bulk writes.
            models.UniqueConstraint(
                models.functions.Lower("email"),
                name="user_email_ci_unique",
            ),
            # Database-level backstop for the role/customer coupling rule.
            models.CheckConstraint(
                check=models.Q(role="customer", customer__isnull=False)
                | models.Q(role__in=["admin", "staff"], customer__isnull=True),
                name="user_role_customer_linkage",
            ),
        ]

    def clean(self):
        super().clean()
        # one canonical form of every email, application-wide
        self.email = self.__class__.objects.normalize_email(self.email).lower()
        if self.customer is not None and self.role != self.Role.CUSTOMER:
            raise ValidationError({"customer": "Only customer-role users may belong to a Customer."})
        if self.role == self.Role.CUSTOMER and self.customer_id is None:
            raise ValidationError(
                {"customer": "A customer-role user must belong to exactly one Customer."}
            )

    def save(self, *args, **kwargs):
        # keep role/is_staff consistent: Admins are Django staff, nobody else is
        self.is_staff = self.role == self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_member_of_staff(self) -> bool:
        return self.role in (self.Role.ADMIN, self.Role.STAFF)

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"
