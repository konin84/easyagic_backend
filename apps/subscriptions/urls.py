from django.urls import path

from .views import (
    MySubscriptionView,
    PaymentConfirmView,
    PaymentInstructionsView,
    PaymentListCreateView,
    PaymentRejectView,
    PlanListView,
    UpgradeRequestView,
    UpgradeView,
)

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="subscription-plans"),
    path("me/", MySubscriptionView.as_view(), name="subscription-me"),
    path("upgrade/", UpgradeView.as_view(), name="subscription-upgrade"),
    path("upgrade-request/", UpgradeRequestView.as_view(), name="subscription-upgrade-request"),
    path("payment-instructions/", PaymentInstructionsView.as_view(), name="payment-instructions"),
    path("payments/", PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/<int:pk>/confirm/", PaymentConfirmView.as_view(), name="payment-confirm"),
    path("payments/<int:pk>/reject/", PaymentRejectView.as_view(), name="payment-reject"),
]
