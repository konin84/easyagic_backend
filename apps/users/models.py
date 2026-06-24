from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    FARMER = "farmer"
    ADMIN = "admin"
    ROLE_CHOICES = [
        (FARMER, "Farmer"),
        (ADMIN, "Admin"),
    ]

    email = models.EmailField(unique=True)

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=FARMER)
    phone = models.CharField(max_length=20, blank=True)
    farm_name = models.CharField(max_length=200, blank=True)
    farm_latitude = models.FloatField(null=True, blank=True)
    farm_longitude = models.FloatField(null=True, blank=True)

    @property
    def is_farmer(self):
        return self.role == self.FARMER

    @property
    def is_admin_user(self):
        return self.role == self.ADMIN

    def __str__(self):
        return f"{self.username} ({self.role})"
