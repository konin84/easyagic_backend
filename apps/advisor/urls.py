from django.urls import path
from .views import AdvisorView

urlpatterns = [
    path("", AdvisorView.as_view(), name="advisor"),
]
