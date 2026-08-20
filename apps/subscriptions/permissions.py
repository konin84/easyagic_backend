from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated

from apps.utils.email_translate import translate_email_content
from .models import Subscription
from .serializers import SubscriptionSerializer


DENIAL_MESSAGES = {
    Subscription.EXPIRED: (
        "Your free trial has ended. Subscribe to a paid plan to keep analyzing your soil."
    ),
    Subscription.QUOTA_EXHAUSTED: (
        "You have used all the soil analyses included in your plan. "
        "Subscribe to a paid plan to analyze more photos."
    ),
    Subscription.CANCELLED: (
        "Your subscription has been cancelled. Renew it to keep analyzing your soil."
    ),
}


class SubscriptionRequired(APIException):
    """402 — the account is authenticated but has no analysis credit left."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "An active subscription is required."

    def __init__(self, payload=None):
        # Assigning `detail` directly skips DRF's ErrorDetail coercion, which would
        # otherwise stringify the numbers the mobile app needs (days left, quota…).
        self.detail = payload if payload is not None else {"error": self.default_detail}


class HasAnalysisCredit(IsAuthenticated):
    """
    Gates the image-analysis endpoints on the caller's subscription.

    Admins and app managers bypass the check. Everyone else needs a subscription
    that is neither expired, cancelled, nor out of quota — a trial being created
    on the spot for any legacy account that predates subscriptions.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        user = request.user
        if user.is_privileged:
            return True

        subscription = Subscription.for_user(user)
        allowed, reason = subscription.check_access()
        if allowed:
            return True

        message = DENIAL_MESSAGES.get(reason, SubscriptionRequired.default_detail)
        raise SubscriptionRequired({
            "error": translate_email_content(message, user.language, is_html=False),
            "code": reason,
            "subscription": SubscriptionSerializer(subscription).data,
        })
