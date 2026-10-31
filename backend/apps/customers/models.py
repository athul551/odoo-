from django.core.exceptions import ValidationError
from django.db import models


class Customer(models.Model):
    """
    The billable organization. Not a login — Customer Users (accounts.User,
    role=customer, one customer each) act on its behalf through the portal.
    Every Subscription, Quotation, Invoice and Payment belongs to a Customer.
    """

    name = models.CharField(max_length=255)
    contact_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(name=""), name="customer_name_not_empty"
            ),
        ]

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Customer name is required."})

    def __str__(self):
        return self.name
