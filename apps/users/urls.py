from django.urls import path
from .views import RegisterView, LoginView, ProfileView, PasswordResetRequestView, PasswordResetVerifyView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("me/", ProfileView.as_view(), name="auth-profile"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("password-reset/verify/", PasswordResetVerifyView.as_view(), name="auth-password-reset-verify"),
]
