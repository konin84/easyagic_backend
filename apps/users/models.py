import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    FARMER = "farmer"
    ADMIN = "admin"
    APP_MANAGER = "appmanager"
    ROLE_CHOICES = [
        (FARMER, "Farmer"),
        (ADMIN, "Admin"),
        (APP_MANAGER, "App Manager"),
    ]

    email = models.EmailField(unique=True)

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=FARMER)
    phone = models.CharField(max_length=20, blank=True)
    farm_name = models.CharField(max_length=200, blank=True)

    @property
    def is_farmer(self):
        return self.role == self.FARMER

    @property
    def is_admin_user(self):
        return self.role == self.ADMIN

    @property
    def is_app_manager(self):
        return self.role == self.APP_MANAGER

    @property
    def is_privileged(self):
        """Staff (superadmin) and app managers bypass location requirements."""
        return self.is_staff or self.role in (self.ADMIN, self.APP_MANAGER)

    def __str__(self):
        return f"{self.username} ({self.role})"


class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def generate_for(cls, user):
        cls.objects.filter(user=user, is_used=False).delete()
        return cls.objects.create(
            user=user,
            code=f"{secrets.randbelow(1_000_000):06d}",
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"OTP({self.user.email}, used={self.is_used})"
