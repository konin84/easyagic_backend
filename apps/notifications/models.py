from django.db import models
from django.conf import settings


class DeviceToken(models.Model):
    ANDROID = "android"
    IOS = "ios"
    PLATFORM_CHOICES = [(ANDROID, "Android"), (IOS, "iOS")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    token = models.TextField(unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"DeviceToken({self.user.email}, {self.platform})"
