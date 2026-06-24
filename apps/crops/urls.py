from django.urls import path
from .views import CropRecommendView

urlpatterns = [
    path("recommend/", CropRecommendView.as_view(), name="crops-recommend"),
]
