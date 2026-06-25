from django.urls import path
from .views import AnalysisHistoryView, AnalysisRecordDetailView

urlpatterns = [
    path("", AnalysisHistoryView.as_view(), name="history-list"),
    path("<int:pk>/", AnalysisRecordDetailView.as_view(), name="history-detail"),
]
