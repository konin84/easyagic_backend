from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/weather/", include("apps.weather.urls")),
    path("api/soil/", include("apps.soil.urls")),
    path("api/crops/", include("apps.crops.urls")),
    path("api/advisor/", include("apps.advisor.urls")),
]
