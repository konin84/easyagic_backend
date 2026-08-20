from django.contrib import admin, messages

from .emails import send_payment_confirmed_email, send_payment_rejected_email
from .models import Payment, PaymentAccount, PlanPrice, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "analyses_used", "analysis_quota", "expires_at")
    list_filter = ("plan", "created_at")
    search_fields = ("user__email", "user__farm_name")
    readonly_fields = ("created_at", "updated_at", "status", "days_remaining", "analyses_remaining")
    raw_id_fields = ("user",)

    @admin.display(description="Status")
    def status(self, obj):
        return obj.status


@admin.register(PlanPrice)
class PlanPriceAdmin(admin.ModelAdmin):
    list_display = ("plan", "currency", "amount", "is_active")
    list_filter = ("currency", "plan", "is_active")
    list_editable = ("amount", "is_active")


@admin.register(PaymentAccount)
class PaymentAccountAdmin(admin.ModelAdmin):
    list_display = ("currency", "bank_name", "account_name", "account_number", "is_active")
    list_filter = ("currency", "is_active")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """The pending queue staff work through each day."""

    list_display = (
        "created_at", "user", "plan", "amount", "currency",
        "method", "reference", "status", "shortfall",
    )
    list_filter = ("status", "method", "currency", "plan", "created_at")
    search_fields = ("user__email", "user__farm_name", "reference")
    raw_id_fields = ("user", "recorded_by", "reviewed_by")
    readonly_fields = (
        "expected_amount", "shortfall", "recorded_by",
        "reviewed_by", "reviewed_at", "created_at", "updated_at",
    )
    actions = ["confirm_payments", "reject_payments"]

    @admin.display(description="Shortfall")
    def shortfall(self, obj):
        return obj.shortfall

    @admin.action(description="Confirm payment and activate the plan")
    def confirm_payments(self, request, queryset):
        confirmed = 0
        for payment in queryset.exclude(status=Payment.CONFIRMED):
            payment.confirm(reviewer=request.user)
            send_payment_confirmed_email(payment)
            confirmed += 1
        self.message_user(
            request, f"{confirmed} payment(s) confirmed and plan(s) activated.", messages.SUCCESS
        )

    @admin.action(description="Reject payment (money not received)")
    def reject_payments(self, request, queryset):
        rejected = 0
        for payment in queryset.exclude(status=Payment.CONFIRMED):
            payment.reject(reviewer=request.user, reason="Payment could not be verified.")
            send_payment_rejected_email(payment)
            rejected += 1
        self.message_user(request, f"{rejected} payment(s) rejected.", messages.SUCCESS)
