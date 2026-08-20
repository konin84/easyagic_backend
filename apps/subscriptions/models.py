import math
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


TRIAL_DAYS = getattr(settings, "TRIAL_DAYS", 14)
TRIAL_ANALYSIS_QUOTA = getattr(settings, "TRIAL_ANALYSIS_QUOTA", 5)


class Subscription(models.Model):
    """
    One subscription per user.

    A farmer starts on a 14-day trial capped at 5 image analyses. Once the trial
    expires or the quota runs out, the analysis endpoints return 402 until an
    admin moves the farmer onto a paid plan.

    Status is derived from `expires_at` / `cancelled_at` rather than stored, so
    it can never go stale and no cron job is needed to expire trials.
    """

    TRIAL = "trial"
    BASIC = "basic"
    PRO = "pro"
    PLAN_CHOICES = [
        (TRIAL, "Free Trial"),
        (BASIC, "Basic"),
        (PRO, "Pro"),
    ]

    # days of access and analysis quota per plan (quota None = unlimited)
    PLAN_CONFIG = {
        TRIAL: {"days": TRIAL_DAYS, "quota": TRIAL_ANALYSIS_QUOTA, "is_paid": False},
        BASIC: {"days": 30, "quota": 30, "is_paid": True},
        PRO: {"days": 30, "quota": None, "is_paid": True},
    }

    ACTIVE = "active"
    EXPIRED = "expired"
    QUOTA_EXHAUSTED = "quota_exhausted"
    CANCELLED = "cancelled"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=TRIAL)
    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Null means the plan never expires."
    )
    analysis_quota = models.PositiveIntegerField(
        null=True, blank=True, help_text="Analyses allowed this period. Null means unlimited."
    )
    analyses_used = models.PositiveIntegerField(default=0)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Subscription({self.user.email}, {self.plan}, {self.status})"

    # ------------------------------------------------------------------ state

    @property
    def is_paid(self):
        return self.PLAN_CONFIG.get(self.plan, {}).get("is_paid", False)

    @property
    def is_trial(self):
        return self.plan == self.TRIAL

    @property
    def has_expired(self):
        return self.expires_at is not None and timezone.now() >= self.expires_at

    @property
    def is_unlimited(self):
        return self.analysis_quota is None

    @property
    def analyses_remaining(self):
        """None when the plan is unlimited."""
        if self.is_unlimited:
            return None
        return max(self.analysis_quota - self.analyses_used, 0)

    @property
    def days_remaining(self):
        """None when the plan never expires."""
        if self.expires_at is None:
            return None
        seconds_left = (self.expires_at - timezone.now()).total_seconds()
        return math.ceil(seconds_left / 86400) if seconds_left > 0 else 0

    @property
    def status(self):
        if self.cancelled_at is not None:
            return self.CANCELLED
        if self.has_expired:
            return self.EXPIRED
        if not self.is_unlimited and self.analyses_remaining == 0:
            return self.QUOTA_EXHAUSTED
        return self.ACTIVE

    @property
    def is_active(self):
        return self.status == self.ACTIVE

    def check_access(self):
        """Return (allowed, reason_code). reason_code is None when allowed."""
        status_now = self.status
        if status_now == self.ACTIVE:
            return True, None
        return False, status_now

    # --------------------------------------------------------------- mutation

    @classmethod
    def start_trial(cls, user):
        """Create the 14-day / 5-analysis trial for a newly registered user."""
        now = timezone.now()
        config = cls.PLAN_CONFIG[cls.TRIAL]
        subscription, _ = cls.objects.get_or_create(
            user=user,
            defaults={
                "plan": cls.TRIAL,
                "started_at": now,
                "expires_at": now + timedelta(days=config["days"]),
                "analysis_quota": config["quota"],
            },
        )
        return subscription

    @classmethod
    def for_user(cls, user):
        """Fetch the user's subscription, starting a trial if they don't have one yet."""
        try:
            return user.subscription
        except cls.DoesNotExist:
            return cls.start_trial(user)

    @classmethod
    def consume_analysis(cls, user):
        """
        Charge one analysis credit. Privileged users and unlimited plans are free.
        Called only after an analysis actually succeeded, so failed Gemini calls
        never cost the farmer a credit.
        """
        if user.is_privileged:
            return
        with transaction.atomic():
            subscription = cls.objects.select_for_update().filter(user=user).first()
            if subscription is None or subscription.is_unlimited:
                return
            subscription.analyses_used = models.F("analyses_used") + 1
            subscription.save(update_fields=["analyses_used", "updated_at"])

    def upgrade(self, plan, months=None, quota=..., reset_usage=True):
        """Move this subscription onto a paid plan and open a fresh billing period."""
        config = self.PLAN_CONFIG.get(plan, {})
        days = 30 * months if months is not None else config.get("days")
        now = timezone.now()

        self.plan = plan
        self.started_at = now
        self.expires_at = now + timedelta(days=days) if days else None
        self.analysis_quota = config.get("quota") if quota is ... else quota
        self.cancelled_at = None
        if reset_usage:
            self.analyses_used = 0
        self.save()
        return self

    def cancel(self):
        self.cancelled_at = timezone.now()
        self.save(update_fields=["cancelled_at", "updated_at"])
        return self


CURRENCY_CHOICES = [
    ("XOF", "CFA Franc BCEAO (XOF)"),
    ("XAF", "CFA Franc BEAC (XAF)"),
    ("NGN", "Nigerian Naira (NGN)"),
    ("GHS", "Ghanaian Cedi (GHS)"),
    ("KES", "Kenyan Shilling (KES)"),
    ("UGX", "Ugandan Shilling (UGX)"),
    ("TZS", "Tanzanian Shilling (TZS)"),
    ("RWF", "Rwandan Franc (RWF)"),
    ("ZAR", "South African Rand (ZAR)"),
    ("ETB", "Ethiopian Birr (ETB)"),
    ("USD", "US Dollar (USD)"),
    ("EUR", "Euro (EUR)"),
]

DEFAULT_CURRENCY = getattr(settings, "DEFAULT_CURRENCY", "XOF")


class PlanPrice(models.Model):
    """
    What a plan costs in a given currency.

    Kept in the database rather than in settings so ops can adjust prices or open
    a new country without a redeploy.
    """

    plan = models.CharField(max_length=20, choices=Subscription.PLAN_CHOICES)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price for one period.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("plan", "currency")]
        ordering = ["currency", "plan"]

    def __str__(self):
        return f"{self.get_plan_display()} — {self.amount} {self.currency}"

    @classmethod
    def lookup(cls, plan, currency):
        return cls.objects.filter(plan=plan, currency=currency, is_active=True).first()


class PaymentAccount(models.Model):
    """Where farmers send money for a given currency — shown by the instructions endpoint."""

    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, unique=True)
    bank_name = models.CharField(max_length=120)
    account_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=64)
    swift_or_iban = models.CharField(max_length=64, blank=True)
    branch = models.CharField(max_length=120, blank=True)
    cash_contact_name = models.CharField(max_length=120, blank=True)
    cash_contact_phone = models.CharField(max_length=32, blank=True)
    instructions = models.TextField(blank=True, help_text="Extra guidance shown to the farmer.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["currency"]

    def __str__(self):
        return f"{self.bank_name} ({self.currency})"


class Payment(models.Model):
    """
    A cash or bank-transfer payment for a plan, confirmed by hand.

    Two ways in:
      * a farmer declares a transfer they made (reference + optional receipt photo)
        → lands as PENDING for staff to verify against the bank statement;
      * an admin or app manager records money they collected themselves
        → recorded as CONFIRMED on the spot, activating the plan immediately.
    """

    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    METHOD_CHOICES = [
        (CASH, "Cash"),
        (BANK_TRANSFER, "Bank Transfer"),
    ]

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (CONFIRMED, "Confirmed"),
        (REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments"
    )
    plan = models.CharField(max_length=20, choices=Subscription.PLAN_CHOICES)
    months = models.PositiveSmallIntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY)
    expected_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Price at the time of declaration, for spotting under/overpayment.",
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference = models.CharField(
        max_length=120, blank=True, help_text="Bank transfer reference or cash receipt number."
    )
    proof = models.ImageField(upload_to="payments/proofs/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    note = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments_recorded",
        help_text="Staff member who collected the money. Null when the farmer declared it.",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return f"Payment({self.user.email}, {self.amount} {self.currency}, {self.status})"

    @property
    def is_pending(self):
        return self.status == self.PENDING

    @property
    def shortfall(self):
        """How much is still owed versus the quoted price. Zero when fully paid."""
        if self.expected_amount is None:
            return None
        return max(self.expected_amount - self.amount, 0)

    def confirm(self, reviewer, activate=True):
        """Mark the money as received and open the farmer's paid period."""
        with transaction.atomic():
            self.status = self.CONFIRMED
            self.reviewed_by = reviewer
            self.reviewed_at = timezone.now()
            self.rejection_reason = ""
            self.save(update_fields=[
                "status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at",
            ])
            if activate:
                Subscription.for_user(self.user).upgrade(plan=self.plan, months=self.months)
        return self

    def reject(self, reviewer, reason=""):
        self.status = self.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=[
            "status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at",
        ])
        return self
