from django.db import models
from django.conf import settings


class AnalysisRecord(models.Model):
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analyses",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    soil_analysis = models.JSONField(null=True)
    weather_data = models.JSONField(null=True)
    crop_recommendations = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Analysis({self.farmer.email}, {self.created_at:%Y-%m-%d})"
