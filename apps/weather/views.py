from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .services import get_agricultural_data


class WeatherView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        lat_raw = request.query_params.get("lat")
        lon_raw = request.query_params.get("lon")

        if not lat_raw or not lon_raw:
            if user.is_privileged:
                return Response({"message": "No location provided. Pass lat and lon query parameters to get weather data."})
            return Response(
                {"error": "lat and lon query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            latitude = float(lat_raw)
            longitude = float(lon_raw)
        except ValueError:
            return Response(
                {"error": "lat and lon must be valid numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = get_agricultural_data(latitude, longitude)
        except Exception as e:
            return Response(
                {"error": f"Failed to fetch weather data: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(data)
