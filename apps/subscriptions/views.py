from django.db import models
from django.utils import timezone

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import User

from .emails import send_payment_confirmed_email, send_payment_rejected_email
from .models import DEFAULT_CURRENCY, Payment, PaymentAccount, PlanPrice, Subscription
from .serializers import (
    PaymentAccountSerializer,
    PaymentCreateSerializer,
    PaymentRejectSerializer,
    PaymentSerializer,
    PlanPriceSerializer,
    SubscriptionSerializer,
    UpgradeRequestSerializer,
    UpgradeSerializer,
)


class IsPrivileged(IsAuthenticated):
    """Admins and app managers only."""

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_privileged


class PlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response([
            {
                "code": code,
                "name": name,
                "duration_days": Subscription.PLAN_CONFIG[code]["days"],
                "analysis_quota": Subscription.PLAN_CONFIG[code]["quota"],
                "is_paid": Subscription.PLAN_CONFIG[code]["is_paid"],
            }
            for code, name in Subscription.PLAN_CHOICES
        ])


class MySubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = Subscription.for_user(request.user)
        return Response(SubscriptionSerializer(subscription).data)


class UpgradeView(APIView):
    """
    POST /api/subscriptions/upgrade/  — admin / app manager only.

    Moves a farmer onto a paid plan. Payment is handled outside the API for now;
    plugging in a gateway later means calling `subscription.upgrade(...)` from a
    webhook instead of from here.
    """

    permission_classes = [IsPrivileged]

    def post(self, request):
        serializer = UpgradeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        lookup = {"pk": data["user_id"]} if data.get("user_id") else {"email": data["email"]}
        try:
            user = User.objects.get(**lookup)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        subscription = Subscription.for_user(user)
        subscription.upgrade(
            plan=data["plan"],
            months=data.get("months"),
            quota=data["analysis_quota"] if "analysis_quota" in data else ...,
        )

        return Response({
            "message": f"{user.email} upgraded to the {subscription.get_plan_display()} plan.",
            "subscription": SubscriptionSerializer(subscription).data,
        })


class PaymentInstructionsView(APIView):
    """
    GET /api/subscriptions/payment-instructions/?currency=XOF

    Everything the farmer needs to pay: what each plan costs in their currency,
    which bank account to transfer to, and who to hand cash to.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        currency = (request.query_params.get("currency") or DEFAULT_CURRENCY).upper()

        prices = PlanPrice.objects.filter(currency=currency, is_active=True)
        account = PaymentAccount.objects.filter(currency=currency, is_active=True).first()

        if not prices.exists():
            return Response(
                {"error": f"No plans are priced in {currency} yet.",
                 "available_currencies": list(
                     PlanPrice.objects.filter(is_active=True)
                     .order_by("currency")
                     .values_list("currency", flat=True)
                     .distinct()
                 )},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "currency": currency,
            "plans": [
                {
                    **PlanPriceSerializer(price).data,
                    "duration_days": Subscription.PLAN_CONFIG[price.plan]["days"],
                    "analysis_quota": Subscription.PLAN_CONFIG[price.plan]["quota"],
                }
                for price in prices
            ],
            "methods": [
                {"code": Payment.BANK_TRANSFER, "name": "Bank Transfer"},
                {"code": Payment.CASH, "name": "Cash"},
            ],
            "account": PaymentAccountSerializer(account).data if account else None,
        })


class PaymentListCreateView(APIView):
    """
    GET  — farmers see their own payments; staff see every payment (?status=, ?method=).
    POST — declare a payment. Staff recording collected money may target another
           user with `email` / `user_id`, and that payment is confirmed immediately.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        payments = Payment.objects.select_related("user", "recorded_by", "reviewed_by")
        if not request.user.is_privileged:
            payments = payments.filter(user=request.user)

        for field in ("status", "method"):
            value = request.query_params.get(field)
            if value:
                payments = payments.filter(**{field: value})

        return Response(PaymentSerializer(payments[:200], many=True).data)

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email, user_id = data.pop("email", None), data.pop("user_id", None)

        target = request.user
        if email or user_id:
            if not request.user.is_privileged:
                return Response(
                    {"error": "You can only declare your own payments."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                target = User.objects.get(**({"pk": user_id} if user_id else {"email": email}))
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Staff recording money they collected are the authority on it — no second review
        collected_by_staff = request.user.is_privileged
        payment = Payment.objects.create(
            user=target,
            recorded_by=request.user if collected_by_staff else None,
            **data,
        )

        if collected_by_staff:
            payment.confirm(reviewer=request.user)
            send_payment_confirmed_email(payment)
            message = f"Payment recorded and {target.email} activated on the {payment.get_plan_display()} plan."
        else:
            message = "Payment submitted. We will confirm it shortly."

        return Response(
            {"message": message, "payment": PaymentSerializer(payment).data},
            status=status.HTTP_201_CREATED,
        )


class PaymentConfirmView(APIView):
    """POST /api/subscriptions/payments/<pk>/confirm/ — staff verified the money arrived."""

    permission_classes = [IsPrivileged]

    def post(self, request, pk):
        payment = Payment.objects.filter(pk=pk).first()
        if payment is None:
            return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
        if payment.status == Payment.CONFIRMED:
            return Response(
                {"error": "This payment is already confirmed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment.confirm(reviewer=request.user)
        send_payment_confirmed_email(payment)

        return Response({
            "message": f"Payment confirmed. {payment.user.email} is now on the {payment.get_plan_display()} plan.",
            "payment": PaymentSerializer(payment).data,
            "subscription": SubscriptionSerializer(Subscription.for_user(payment.user)).data,
        })


class PaymentRejectView(APIView):
    """POST /api/subscriptions/payments/<pk>/reject/ — the money never arrived."""

    permission_classes = [IsPrivileged]

    def post(self, request, pk):
        payment = Payment.objects.filter(pk=pk).first()
        if payment is None:
            return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
        if payment.status == Payment.CONFIRMED:
            return Response(
                {"error": "A confirmed payment cannot be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PaymentRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment.reject(reviewer=request.user, reason=serializer.validated_data["reason"])
        send_payment_rejected_email(payment)

        return Response({
            "message": "Payment rejected.",
            "payment": PaymentSerializer(payment).data,
        })


class UpgradeRequestView(APIView):
    """
    POST /api/subscriptions/upgrade-request/ — the farmer asks to go paid.

    Creates a PENDING payment and changes nothing else: the farmer stays on their
    current plan, and the paywall stays shut until an admin or app manager
    confirms the money arrived via /payments/<pk>/confirm/.

    The response carries the amount owed and where to send it, so the app can show
    the payment instructions on the same screen.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.is_privileged:
            return Response(
                {"error": "Staff accounts are not metered. Use /subscriptions/upgrade/ to move a farmer onto a plan."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UpgradeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # An earlier request that was only ever an intent gets superseded, so a farmer
        # can change their mind. A declared payment (reference or receipt attached) is
        # evidence and is left alone for staff to rule on.
        (
            Payment.objects
            .filter(user=request.user, status=Payment.PENDING, reference="", recorded_by__isnull=True)
            .filter(models.Q(proof="") | models.Q(proof__isnull=True))
            .update(
                status=Payment.REJECTED,
                rejection_reason="Superseded by a newer upgrade request.",
                reviewed_at=timezone.now(),
            )
        )

        payment = Payment.objects.create(user=request.user, **serializer.validated_data)
        account = PaymentAccount.objects.filter(currency=payment.currency, is_active=True).first()

        return Response(
            {
                "message": "Upgrade requested. Your plan will start as soon as we confirm your payment.",
                "amount_due": payment.amount,
                "currency": payment.currency,
                "payment": PaymentSerializer(payment).data,
                "account": PaymentAccountSerializer(account).data if account else None,
                "subscription": SubscriptionSerializer(Subscription.for_user(request.user)).data,
            },
            status=status.HTTP_201_CREATED,
        )
