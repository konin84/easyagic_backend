from django.contrib import admin
from django.urls import path, include
from config.exceptions import handler500  # noqa: F401 — picked up by Django automatically

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/weather/", include("apps.weather.urls")),
    path("api/soil/", include("apps.soil.urls")),
    path("api/crops/", include("apps.crops.urls")),
    path("api/advisor/", include("apps.advisor.urls")),
    path("api/history/", include("apps.history.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
]
