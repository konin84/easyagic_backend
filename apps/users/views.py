import secrets
import string

from django.db import models

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken

from apps.subscriptions.models import Payment, Subscription

from .models import User, OTP
from .permissions import IsPlatformAdmin
from .serializers import (
    AdminUserSerializer,
    LoginSerializer,
    RegisterAppManagerSerializer,
    RegisterSerializer,
    UserProfileSerializer,
)
from .emails import send_welcome_email, send_otp_email

_PASSWORD_CHARS = string.ascii_letters + string.digits + "!@#$%"


def _generate_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_CHARS) for _ in range(length))


def _jwt_response(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserProfileSerializer(user).data,
    }


class LanguageListView(APIView):
    def get(self, request):
        return Response([
            {"code": code, "name": name}
            for code, name in User.LANGUAGE_CHOICES
        ])


class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        password = _generate_password()
        user = serializer.save(password=password)
        Subscription.start_trial(user)

        send_welcome_email(user, password)

        return Response(_jwt_response(user), status=status.HTTP_201_CREATED)


class RegisterAppManagerView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        serializer = RegisterAppManagerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        password = _generate_password()
        user = serializer.save(password=password)

        send_welcome_email(user, password)

        return Response(
            {
                "message": "App manager account created. Credentials sent by email.",
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]
        return Response(_jwt_response(user))


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")

        if not current_password or not new_password:
            return Response(
                {"error": "current_password and new_password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(current_password):
            return Response(
                {"error": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {"error": "new_password must be at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])

        return Response(
            {"message": "Password updated successfully.", **_jwt_response(request.user)}
        )


class PasswordResetRequestView(APIView):
    def post(self, request):
        email = request.data.get("email", "").strip()
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
            otp = OTP.generate_for(user)
            send_otp_email(user, otp.code)
        except User.DoesNotExist:
            pass

        return Response({"message": "If this email is registered, a reset code has been sent."})


class PasswordResetVerifyView(APIView):
    def post(self, request):
        email = request.data.get("email", "").strip()
        code = request.data.get("otp", "").strip()
        new_password = request.data.get("new_password", "")

        if not all([email, code, new_password]):
            return Response(
                {"error": "email, otp, and new_password are all required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {"error": "new_password must be at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "Invalid code."}, status=status.HTTP_400_BAD_REQUEST)

        otp = OTP.objects.filter(user=user, code=code, is_used=False).first()
        if not otp or not otp.is_valid():
            return Response({"error": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        otp.is_used = True
        otp.save(update_fields=["is_used"])

        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response({
            "message": "Password reset successful.",
            **_jwt_response(user),
        })


def _deletion_impact(user):
    """
    What would be destroyed along with this account, straight from Django's own
    collector — so it stays accurate if new related models are added later.
    """
    from django.db.models.deletion import Collector

    collector = Collector(using="default")
    collector.collect([user])

    impact = {}

    def add(model, count):
        if model is User or not count:
            return
        impact[model._meta.label] = impact.get(model._meta.label, 0) + count

    for model, instances in collector.data.items():
        add(model, len(instances))
    # Rows Django can drop with a single query never land in `data`
    for queryset in collector.fast_deletes:
        add(queryset.model, queryset.count())

    return impact


class AdminUserListView(APIView):
    """
    GET /api/auth/users/ — platform admins list accounts so they can find the one
    to act on, newest first.

    Filters: ?role=farmer|admin|appmanager, ?is_active=true|false, ?search=<email>
    Paging:  ?limit= (default 100, max 500), ?offset=

    `count` is the total matching the filters, not the size of this page, so it is
    always clear when more accounts exist than are being shown.
    """

    permission_classes = [IsPlatformAdmin]

    DEFAULT_LIMIT = 100
    MAX_LIMIT = 500

    def get(self, request):
        users = User.objects.select_related("subscription").order_by("-date_joined")

        role = request.query_params.get("role")
        if role:
            users = users.filter(role=role)

        is_active = request.query_params.get("is_active")
        if is_active is not None:
            users = users.filter(is_active=is_active.lower() in ("1", "true", "yes"))

        search = request.query_params.get("search")
        if search:
            users = users.filter(models.Q(email__icontains=search) | models.Q(farm_name__icontains=search))

        try:
            limit = min(int(request.query_params.get("limit", self.DEFAULT_LIMIT)), self.MAX_LIMIT)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            return Response(
                {"error": "limit and offset must be whole numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        limit = max(limit, 1)

        total = users.count()
        page = users[offset:offset + limit]

        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": AdminUserSerializer(page, many=True).data,
        })


class AdminUserDetailView(APIView):
    """
    Platform-admin account management.

      GET    — the account plus exactly what deleting it would destroy
      PATCH  — deactivate / reactivate ({"is_active": false}); the reversible option
      DELETE — permanently remove the account and everything cascading from it
    """

    permission_classes = [IsPlatformAdmin]

    def _get_user(self, pk):
        return User.objects.filter(pk=pk).first()

    def get(self, request, pk):
        user = self._get_user(pk)
        if user is None:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "user": AdminUserSerializer(user).data,
            "deletion_impact": _deletion_impact(user),
        })

    def patch(self, request, pk):
        user = self._get_user(pk)
        if user is None:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if "is_active" not in request.data:
            return Response(
                {"error": "Send is_active (true or false)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_active = request.data["is_active"]
        if isinstance(is_active, str):
            is_active = is_active.lower() in ("1", "true", "yes")

        if not is_active:
            blocked = self._blocked_from_losing_access(request, user)
            if blocked:
                return Response({"error": blocked}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = bool(is_active)
        user.save(update_fields=["is_active"])

        return Response({
            "message": f"{user.email} has been {'reactivated' if user.is_active else 'deactivated'}.",
            "user": AdminUserSerializer(user).data,
        })

    def delete(self, request, pk):
        user = self._get_user(pk)
        if user is None:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        blocked = self._blocked_from_losing_access(request, user)
        if blocked:
            return Response({"error": blocked}, status=status.HTTP_400_BAD_REQUEST)

        # Deleting a farmer cascades their confirmed payments away — that is
        # accounting data, so it needs saying out loud rather than happening quietly.
        confirmed = Payment.objects.filter(user=user, status=Payment.CONFIRMED).count()
        force = request.query_params.get("force", "").lower() in ("1", "true", "yes")
        if confirmed and not force:
            return Response(
                {
                    "error": (
                        f"{user.email} has {confirmed} confirmed payment(s). Deleting the account "
                        "would destroy those financial records."
                    ),
                    "confirmed_payments": confirmed,
                    "deletion_impact": _deletion_impact(user),
                    "hint": (
                        "Deactivate the account instead (PATCH with is_active=false), which keeps "
                        "the records, or repeat this call with ?force=true to delete anyway."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        email = user.email
        impact = _deletion_impact(user)
        user.delete()

        return Response({
            "message": f"{email} and all associated data have been permanently deleted.",
            "deleted": impact,
        })

    def _blocked_from_losing_access(self, request, target):
        """
        Reason this account must not be removed, or None when it's safe.

        Refusing self-deletion is on its own enough to guarantee at least one
        platform admin always survives: the caller is an active admin and cannot
        remove themselves, so an admin remains no matter who else they delete.
        """
        if target.pk == request.user.pk:
            return "You cannot delete or deactivate your own account."
        return None
