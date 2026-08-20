from rest_framework import serializers

from .models import Payment, PaymentAccount, PlanPrice, Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    is_trial = serializers.BooleanField(read_only=True)
    is_paid = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True, allow_null=True)
    analyses_remaining = serializers.IntegerField(read_only=True, allow_null=True)
    plan_display = serializers.CharField(source="get_plan_display", read_only=True)
    pending_upgrade = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "plan", "plan_display", "status",
            "is_trial", "is_paid", "is_active",
            "started_at", "expires_at", "days_remaining",
            "analysis_quota", "analyses_used", "analyses_remaining",
            "cancelled_at", "pending_upgrade",
        ]
        read_only_fields = fields

    def get_pending_upgrade(self, subscription):
        """The plan the farmer has asked for but staff haven't confirmed yet."""
        pending = (
            Payment.objects.filter(user_id=subscription.user_id, status=Payment.PENDING)
            .order_by("-created_at")
            .first()
        )
        return PaymentSerializer(pending).data if pending else None


class UpgradeSerializer(serializers.Serializer):
    """Admin-driven upgrade. Identify the farmer by id or email."""

    user_id = serializers.IntegerField(required=False)
    email = serializers.EmailField(required=False)
    plan = serializers.ChoiceField(
        choices=[p for p, _ in Subscription.PLAN_CHOICES if p != Subscription.TRIAL]
    )
    months = serializers.IntegerField(required=False, min_value=1, max_value=36)
    analysis_quota = serializers.IntegerField(required=False, min_value=0, allow_null=True)

    def validate(self, data):
        if not data.get("user_id") and not data.get("email"):
            raise serializers.ValidationError("Provide either user_id or email.")
        return data


class PlanPriceSerializer(serializers.ModelSerializer):
    plan_display = serializers.CharField(source="get_plan_display", read_only=True)

    class Meta:
        model = PlanPrice
        fields = ["plan", "plan_display", "currency", "amount"]


class PaymentAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAccount
        fields = [
            "currency", "bank_name", "account_name", "account_number",
            "swift_or_iban", "branch",
            "cash_contact_name", "cash_contact_phone", "instructions",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    plan_display = serializers.CharField(source="get_plan_display", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    shortfall = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    recorded_by_email = serializers.EmailField(source="recorded_by.email", read_only=True, default=None)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = [
            "id", "user_email", "plan", "plan_display", "months",
            "amount", "currency", "expected_amount", "shortfall",
            "method", "method_display", "reference", "proof", "note",
            "status", "rejection_reason",
            "recorded_by_email", "reviewed_by_email", "reviewed_at",
            "created_at",
        ]
        read_only_fields = fields


class PaymentCreateSerializer(serializers.ModelSerializer):
    """
    Farmers declare their own payment. Staff may pass `email` or `user_id` to record
    money they collected on someone's behalf.
    """

    email = serializers.EmailField(required=False, write_only=True)
    user_id = serializers.IntegerField(required=False, write_only=True)

    class Meta:
        model = Payment
        fields = [
            "plan", "months", "amount", "currency", "method",
            "reference", "proof", "note", "email", "user_id",
        ]
        extra_kwargs = {
            "amount": {"required": False},
            "months": {"required": False},
        }

    def validate_plan(self, plan):
        if not Subscription.PLAN_CONFIG.get(plan, {}).get("is_paid"):
            raise serializers.ValidationError("Choose a paid plan.")
        return plan

    def validate(self, data):
        plan, currency = data["plan"], data.get("currency", Payment._meta.get_field("currency").default)
        months = data.get("months") or 1

        price = PlanPrice.lookup(plan, currency)
        if price is None:
            raise serializers.ValidationError({
                "currency": f"No active price for the {plan} plan in {currency}."
            })

        data["currency"] = currency
        data["months"] = months
        data["expected_amount"] = price.amount * months
        # A farmer who doesn't type an amount is quoted the list price
        data.setdefault("amount", data["expected_amount"])

        if data["amount"] <= 0:
            raise serializers.ValidationError({"amount": "Amount must be greater than zero."})

        if data["method"] == Payment.BANK_TRANSFER and not data.get("reference") and not data.get("proof"):
            raise serializers.ValidationError({
                "reference": "Give the transfer reference or attach a photo of the receipt."
            })

        return data


class PaymentRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class UpgradeRequestSerializer(serializers.ModelSerializer):
    """
    A farmer asking to move onto a paid plan, before any money has changed hands.

    Unlike PaymentCreateSerializer this asserts nothing about a payment already
    made, so no reference or receipt is required — `method` is only how they
    intend to pay. Nothing activates until staff confirm.
    """

    class Meta:
        model = Payment
        fields = ["plan", "months", "currency", "method", "note"]
        extra_kwargs = {"months": {"required": False}}

    def validate_plan(self, plan):
        if not Subscription.PLAN_CONFIG.get(plan, {}).get("is_paid"):
            raise serializers.ValidationError("Choose a paid plan.")
        return plan

    def validate(self, data):
        currency = data.get("currency", Payment._meta.get_field("currency").default)
        months = data.get("months") or 1

        price = PlanPrice.lookup(data["plan"], currency)
        if price is None:
            raise serializers.ValidationError({
                "currency": f"No active price for the {data['plan']} plan in {currency}."
            })

        data["currency"] = currency
        data["months"] = months
        data["amount"] = price.amount * months
        data["expected_amount"] = data["amount"]
        return data
