from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import get_crop_recommendations
from .data import CROP_DATABASE


class CropRecommendView(APIView):
    def get(self, request):
        soil_type = request.query_params.get("soil_type", "Unknown")
        temp_str = request.query_params.get("temp")

        current_temp = None
        if temp_str:
            try:
                current_temp = float(temp_str)
            except ValueError:
                return Response(
                    {"error": "temp must be a number (°C)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if soil_type not in CROP_DATABASE:
            return Response(
                {
                    "error": f"Unknown soil_type '{soil_type}'.",
                    "valid_types": list(CROP_DATABASE.keys()),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        recommendations = get_crop_recommendations(soil_type, current_temp)
        return Response({"soil_type": soil_type, "recommendations": recommendations})
