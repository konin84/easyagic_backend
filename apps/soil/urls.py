from django.urls import path
from .views import SoilAnalysisView

urlpatterns = [
    path("analyze/", SoilAnalysisView.as_view(), name="soil-analyze"),
]
