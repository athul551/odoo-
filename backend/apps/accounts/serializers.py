"""
Identity serializers: sign-up, profile, password reset/change.

Sign-up is the one place a Customer is created together with its first
Customer User, so the two writes must be atomic — a duplicate email must not
leave an orphan organization behind (ADR 0003 + one-Customer-per-portal).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.customers.models import Customer

User = get_user_model()


class CustomerSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    customer = CustomerSummarySerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "role_display",
            "customer", "is_active", "date_joined", "last_login",
        ]
        read_only_fields = ["id", "email", "role", "customer", "is_active",
                            "date_joined", "last_login"]


class RegisterSerializer(serializers.Serializer):
    """
    Public customer sign-up. Creates the Customer organization and its first
    Customer User in one transaction; role is always CUSTOMER (staff/admin are
    created by an Admin, never through the public door).
    """

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    organization_name = serializers.CharField(max_length=255)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        # The functional unique index is the backstop; this is the friendly error.
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate_organization_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Organization name is required.")
        return value.strip()

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": ["Passwords do not match."]}
            )
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        customer = Customer(
            name=validated_data["organization_name"],
            contact_email=validated_data.get("contact_email") or validated_data["email"],
            phone=validated_data.get("phone", ""),
        )
        customer.full_clean()
        customer.save()
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=User.Role.CUSTOMER,
            customer=customer,
        )


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Customers/staff may rename themselves; role, email and Customer are fixed."""

    class Meta:
        model = User
        fields = ["first_name", "last_name"]


class StaffUserCreateSerializer(serializers.Serializer):
    """
    Admin-only staff provisioning (CONTEXT.md: only an Admin creates Users).
    Customer accounts are born through public sign-up, never here.
    """

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    role = serializers.ChoiceField(choices=[User.Role.STAFF, User.Role.ADMIN])
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": ["Passwords do not match."]}
            )
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        return User.objects.create_user(**validated_data)


class StaffUserUpdateSerializer(serializers.ModelSerializer):
    """Admins may deactivate or rename colleagues, never their own account."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "is_active"]

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.user.pk == self.instance.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError(
                    {"is_active": ["You cannot deactivate your own account."]}
                )
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": ["Passwords do not match."]}
            )
        try:
            validate_password(attrs["new_password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": ["Passwords do not match."]}
            )
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": ["Choose a password different from the current one."]}
            )
        try:
            validate_password(attrs["new_password"], self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs
