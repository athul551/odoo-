"""
Authentication endpoints: sign-up, login, logout, profile, password flows.

Login issues a JWT pair (SimpleJWT). Password reset always answers 200 so the
endpoint cannot be used to enumerate accounts; the email itself carries a
single-use token built by Django's ``default_token_generator``.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.common.permissions import IsAdminOnly

from .serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    StaffUserCreateSerializer,
    StaffUserUpdateSerializer,
    UserSerializer,
)

User = get_user_model()

RESET_LINK_TEMPLATE = (
    "{base}/reset-password?uid={uid}&token={token}"
)


def _issue_tokens(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _revoke_all_tokens(user) -> None:
    """
    Password change/reset invalidates every outstanding refresh token. Access
    tokens live <=30 minutes, so a stolen session dies out quickly after this.
    """
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class LoginSerializer(TokenObtainPairSerializer):
    """JWT pair plus the profile the SPA needs to route by role."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    serializer_class = LoginSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Sign the new customer straight in — one less round trip, same tokens.
        payload = {"user": UserSerializer(user).data, **_issue_tokens(user)}
        return Response(payload, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    """
    Blacklists the presented refresh token. Idempotent-ish: an already dead
    token answers 200 so a client can always clear its local session.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw = request.data.get("refresh")
        if not raw:
            return Response(
                {"errors": {"refresh": ["A refresh token is required."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(raw).blacklist()
        except Exception:  # expired, malformed or already blacklisted
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = RESET_LINK_TEMPLATE.format(
                base=settings.FRONTEND_BASE_URL.rstrip("/"), uid=uid, token=token
            )
            send_mail(
                subject="Reset your Brightloop password",
                message=(
                    "We received a request to reset your Brightloop password.\n\n"
                    f"Open this link to choose a new one:\n{link}\n\n"
                    "The link expires shortly and can be used once. "
                    "If you did not ask for this, ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        # Identical answer whether or not the address exists.
        return Response(
            {"detail": "If that email belongs to an account, a reset link is on its way."}
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user_id = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, data["token"]):
            return Response(
                {"errors": {"token": ["This reset link is invalid or has expired."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        _revoke_all_tokens(user)
        return Response({"detail": "Password updated. Sign in with the new password."})


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        _revoke_all_tokens(user)
        return Response({"detail": "Password updated.", **_issue_tokens(user)})


class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Admin-only user administration: provision staff/admins, deactivate people.
    Customer accounts are created by public sign-up only, so role=customer is
    refused here — one customer, one portal account.
    """

    permission_classes = [IsAdminOnly]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = User.objects.select_related("customer").order_by("email")
        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(role=role)
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(email__icontains=search)
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return StaffUserCreateSerializer
        if self.action in ("update", "partial_update"):
            return StaffUserUpdateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(instance).data)
