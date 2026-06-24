from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import get_agricultural_data


class WeatherView(APIView):
    def get(self, request):
        latitude = request.query_params.get("lat")
        longitude = request.query_params.get("lon")

        if not latitude or not longitude:
            return Response(
                {"error": "lat and lon query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            latitude = float(latitude)
            longitude = float(longitude)
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
