from rest_framework import serializers
from .models import AnalysisRecord


class AnalysisRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisRecord
        fields = [
            "id", "created_at", "latitude", "longitude",
            "soil_analysis", "weather_data", "crop_recommendations",
        ]
        read_only_fields = fields
