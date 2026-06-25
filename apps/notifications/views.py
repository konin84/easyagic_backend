from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import DeviceToken


class RegisterDeviceTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("token", "").strip()
        platform = request.data.get("platform", "").strip().lower()

        if not token:
            return Response({"error": "token is required."}, status=status.HTTP_400_BAD_REQUEST)
        if platform not in (DeviceToken.ANDROID, DeviceToken.IOS):
            return Response(
                {"error": "platform must be 'android' or 'ios'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        DeviceToken.objects.update_or_create(
            token=token,
            defaults={"user": request.user, "platform": platform},
        )
        return Response({"message": "Device registered."})


class UnregisterDeviceTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"error": "token is required."}, status=status.HTTP_400_BAD_REQUEST)

        DeviceToken.objects.filter(user=request.user, token=token).delete()
        return Response({"message": "Device unregistered."})
