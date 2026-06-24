import concurrent.futures

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.weather.services import get_agricultural_data
from apps.soil.services import analyze_soil_image
from apps.crops.services import get_crop_recommendations
from .emails import send_advice_email


class AdvisorView(APIView):
    """
    Single endpoint for the mobile app.

    POST multipart/form-data:
      image    — photo of the soil (required)
      lat      — GPS latitude  (required)
      lon      — GPS longitude (required)

    Returns soil analysis, weather/soil-temp data, and ranked crop recommendations.
    The full report is also emailed to the authenticated farmer in the background.
    """

    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        errors = {}

        if "image" not in request.FILES:
            errors["image"] = "A soil photo is required."

        user = request.user
        lat_str = request.data.get("lat")
        lon_str = request.data.get("lon")

        if not lat_str and not user.is_staff:
            errors["lat"] = "GPS latitude is required."
        if not lon_str and not user.is_staff:
            errors["lon"] = "GPS longitude is required."

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        latitude = longitude = None
        if lat_str and lon_str:
            try:
                latitude = float(lat_str)
                longitude = float(lon_str)
            except ValueError:
                return Response(
                    {"error": "lat and lon must be valid numbers."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        image_file = request.FILES["image"]
        if not image_file.content_type.startswith("image/"):
            return Response(
                {"error": "Uploaded file must be an image."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        image_bytes = image_file.read()

        # Run soil analysis and weather fetch in parallel (weather skipped if no coordinates)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            soil_future = executor.submit(analyze_soil_image, image_bytes)
            weather_future = (
                executor.submit(get_agricultural_data, latitude, longitude)
                if latitude is not None and longitude is not None
                else None
            )

            soil_error = weather_error = None
            try:
                soil_analysis = soil_future.result(timeout=30)
            except Exception as e:
                soil_error = str(e)
                soil_analysis = None

            weather_data = None
            if weather_future is not None:
                try:
                    weather_data = weather_future.result(timeout=15)
                except Exception as e:
                    weather_error = str(e)

        if soil_error and weather_error:
            return Response(
                {"error": "Both soil analysis and weather fetch failed.", "details": {"soil": soil_error, "weather": weather_error}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Derive crop recommendations from what we have
        soil_type = (soil_analysis or {}).get("soil_type", "Unknown")
        current_temp = None
        if weather_data:
            current_temp = weather_data.get("current_weather", {}).get("temperature_2m")

        crop_recommendations = get_crop_recommendations(soil_type, current_temp)

        response = {
            "soil_analysis": soil_analysis,
            "weather": weather_data,
            "crop_recommendations": crop_recommendations,
        }

        if soil_error:
            response["warnings"] = {"soil_analysis": f"Soil analysis failed: {soil_error}"}
        if weather_error:
            response.setdefault("warnings", {})["weather"] = f"Weather fetch failed: {weather_error}"

        # Email the report to the farmer without blocking the API response
        send_advice_email(request.user, response)

        return Response(response)
