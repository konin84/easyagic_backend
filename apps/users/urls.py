from django.urls import path
from .views import RegisterView, LoginView, ProfileView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("me/", ProfileView.as_view(), name="auth-profile"),
]
