from django.urls import path
from .views import RegisterDeviceTokenView, UnregisterDeviceTokenView

urlpatterns = [
    path("register/", RegisterDeviceTokenView.as_view(), name="notifications-register"),
    path("unregister/", UnregisterDeviceTokenView.as_view(), name="notifications-unregister"),
]
