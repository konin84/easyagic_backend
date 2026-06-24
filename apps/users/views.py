import secrets
import string

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated

from .models import User, OTP
from .serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer
from .emails import send_welcome_email, send_otp_email

_PASSWORD_CHARS = string.ascii_letters + string.digits + "!@#$%"


def _generate_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_CHARS) for _ in range(length))


class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        password = _generate_password()
        user = serializer.save(password=password)

        send_welcome_email(user, password)

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "message": "Account created. Check your email for your login password.",
                "token": token.key,
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
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": UserProfileSerializer(user).data,
            }
        )


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


class PasswordResetRequestView(APIView):
    def post(self, request):
        email = request.data.get("email", "").strip()
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Always return the same message so we don't reveal whether the email exists
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

        # Rotate the auth token so old sessions are invalidated
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)

        return Response({
            "message": "Password reset successful.",
            "token": token.key,
        })
