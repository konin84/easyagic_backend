from django.urls import path
from .views import StatsView, FarmerListView, FarmerDetailView

urlpatterns = [
    path("stats/", StatsView.as_view(), name="dashboard-stats"),
    path("farmers/", FarmerListView.as_view(), name="dashboard-farmers"),
    path("farmers/<int:pk>/", FarmerDetailView.as_view(), name="dashboard-farmer-detail"),
]
