from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView,
    RegisterAppManagerView,
    LoginView,
    ProfileView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("register/app-manager/", RegisterAppManagerView.as_view(), name="auth-register-app-manager"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("me/", ProfileView.as_view(), name="auth-profile"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("password-reset/verify/", PasswordResetVerifyView.as_view(), name="auth-password-reset-verify"),
]
