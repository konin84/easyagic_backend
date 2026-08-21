import json
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import User

from .models import Payment, PaymentAccount, PlanPrice, Subscription

FAKE_SOIL = {"soil_type": "Loam", "texture": "Fine", "confidence": 0.9}


def image_upload():
    """A real 1x1 PNG — ImageField runs Pillow validation, so fake bytes won't do."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "#8b5a2b").save(buffer, format="PNG")
    return ("image", ("soil.png", buffer.getvalue(), "image/png"))


def sync_emails():
    """
    Emails are delivered from a daemon thread, so `mail.outbox` is racy to assert on.
    Swap the async sender for a direct call to the same delivery function.
    """
    from apps.users.emails import _deliver

    return patch("apps.subscriptions.emails._send_async", side_effect=_deliver)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SubscriptionFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    # -------------------------------------------------------------- helpers

    def register_farmer(self, email="farmer@example.com"):
        response = self.client.post(
            reverse("auth-register"),
            {"email": email, "farm_name": "Test Farm", "language": "en"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email=email)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return user, response

    def analyze(self):
        name, payload = image_upload()
        with patch("apps.soil.views.analyze_soil_image", return_value=FAKE_SOIL):
            return self.client.post(
                reverse("soil-analyze"), {name: _file(payload)}, format="multipart"
            )

    # ------------------------------------------------------------- the trial

    def test_registration_starts_14_day_5_analysis_trial(self):
        user, response = self.register_farmer()
        subscription = user.subscription

        self.assertEqual(subscription.plan, Subscription.TRIAL)
        self.assertEqual(subscription.status, Subscription.ACTIVE)
        self.assertEqual(subscription.analysis_quota, 5)
        self.assertEqual(subscription.analyses_used, 0)
        self.assertEqual(subscription.days_remaining, 14)
        # the mobile app receives the trial state in the register/login payload
        self.assertEqual(response.data["user"]["subscription"]["analyses_remaining"], 5)

    def test_five_analyses_allowed_then_402(self):
        user, _ = self.register_farmer()

        for expected_left in (4, 3, 2, 1, 0):
            response = self.analyze()
            self.assertEqual(response.status_code, 200, response.data)
            user.subscription.refresh_from_db()
            self.assertEqual(user.subscription.analyses_remaining, expected_left)

        response = self.analyze()
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.data["code"], Subscription.QUOTA_EXHAUSTED)
        self.assertEqual(response.data["subscription"]["analyses_used"], 5)

    def test_expired_trial_blocks_even_with_quota_left(self):
        user, _ = self.register_farmer()
        Subscription.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(days=1)
        )

        response = self.analyze()
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.data["code"], Subscription.EXPIRED)
        user.subscription.refresh_from_db()
        self.assertEqual(user.subscription.analyses_used, 0)

    def test_failed_analysis_does_not_consume_a_credit(self):
        user, _ = self.register_farmer()
        name, payload = image_upload()

        with patch("apps.soil.views.analyze_soil_image", side_effect=RuntimeError("Gemini down")):
            response = self.client.post(
                reverse("soil-analyze"), {name: _file(payload)}, format="multipart"
            )

        self.assertEqual(response.status_code, 502)
        user.subscription.refresh_from_db()
        self.assertEqual(user.subscription.analyses_used, 0)

    def test_advisor_endpoint_is_metered_too(self):
        user, _ = self.register_farmer()
        name, payload = image_upload()

        with patch("apps.advisor.views.analyze_soil_image", return_value=FAKE_SOIL), \
             patch("apps.advisor.views.get_agricultural_data", return_value={"current_weather": {"temperature_2m": 27}}), \
             patch("apps.advisor.views.AnalysisRecord"), \
             patch("apps.advisor.views.send_advice_email"), \
             patch("apps.advisor.views.send_push_to_user"):
            response = self.client.post(
                reverse("advisor"),
                {name: _file(payload), "lat": "5.35", "lon": "-4.02"},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200, response.data)
        user.subscription.refresh_from_db()
        self.assertEqual(user.subscription.analyses_used, 1)

    # ------------------------------------------------------- privileged bypass

    def test_admin_is_never_metered(self):
        admin = User.objects.create_superuser(
            username="boss@example.com", email="boss@example.com",
            password="x" * 12, role=User.ADMIN,
        )
        self.client.force_authenticate(user=admin)

        for _ in range(7):
            self.assertEqual(self.analyze().status_code, 200)

        self.assertFalse(Subscription.objects.filter(user=admin).exists())

    # -------------------------------------------------------------- upgrading

    def test_admin_upgrade_restores_access(self):
        farmer, _ = self.register_farmer()
        Subscription.objects.filter(user=farmer).update(analyses_used=5)

        self.assertEqual(self.analyze().status_code, 402)

        admin = User.objects.create_superuser(
            username="boss@example.com", email="boss@example.com",
            password="x" * 12, role=User.ADMIN,
        )
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        response = admin_client.post(
            reverse("subscription-upgrade"),
            {"email": farmer.email, "plan": Subscription.PRO, "months": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        farmer.subscription.refresh_from_db()
        self.assertEqual(farmer.subscription.plan, Subscription.PRO)
        self.assertTrue(farmer.subscription.is_paid)
        self.assertIsNone(farmer.subscription.analyses_remaining)  # unlimited

        self.assertEqual(self.analyze().status_code, 200)

    def test_farmer_cannot_upgrade_themselves(self):
        farmer, _ = self.register_farmer()
        response = self.client.post(
            reverse("subscription-upgrade"),
            {"email": farmer.email, "plan": Subscription.PRO},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_basic_plan_grants_a_fresh_monthly_quota(self):
        farmer, _ = self.register_farmer()
        farmer.subscription.upgrade(plan=Subscription.BASIC)

        subscription = Subscription.objects.get(user=farmer)
        self.assertEqual(subscription.analysis_quota, 30)
        self.assertEqual(subscription.analyses_used, 0)
        self.assertEqual(subscription.days_remaining, 30)

    def test_me_endpoint_reports_remaining_credits(self):
        farmer, _ = self.register_farmer()
        self.analyze()

        response = self.client.get(reverse("subscription-me"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["plan"], Subscription.TRIAL)
        self.assertEqual(response.data["analyses_remaining"], 4)
        self.assertEqual(response.data["status"], Subscription.ACTIVE)

    def test_legacy_user_without_subscription_gets_a_trial_on_first_call(self):
        legacy = User.objects.create_user(
            username="old@example.com", email="old@example.com",
            password="x" * 12, role=User.FARMER,
        )
        self.assertFalse(Subscription.objects.filter(user=legacy).exists())

        self.client.force_authenticate(user=legacy)
        self.assertEqual(self.analyze().status_code, 200)

        subscription = Subscription.objects.get(user=legacy)
        self.assertEqual(subscription.plan, Subscription.TRIAL)
        self.assertEqual(subscription.analyses_used, 1)


def _file(payload):
    from django.core.files.uploadedfile import SimpleUploadedFile
    filename, content, content_type = payload
    return SimpleUploadedFile(filename, content, content_type=content_type)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ManualPaymentTests(TestCase):
    """Cash and bank-transfer payments, confirmed by hand."""

    def setUp(self):
        self.client = APIClient()
        PlanPrice.objects.create(plan=Subscription.PRO, currency="XOF", amount=15000)
        PlanPrice.objects.create(plan=Subscription.BASIC, currency="XOF", amount=5000)
        PlanPrice.objects.create(plan=Subscription.PRO, currency="NGN", amount=40000)
        PaymentAccount.objects.create(
            currency="XOF", bank_name="Ecobank CI", account_name="EasyAgric SARL",
            account_number="CI0012345678", cash_contact_phone="+225 07 00 00 00",
        )

        self.farmer = User.objects.create_user(
            username="paye@example.com", email="paye@example.com",
            password="x" * 12, role=User.FARMER,
        )
        Subscription.start_trial(self.farmer)
        # trial already spent, so the paywall is closed
        Subscription.objects.filter(user=self.farmer).update(analyses_used=5)

        self.staff = User.objects.create_user(
            username="agent@example.com", email="agent@example.com",
            password="x" * 12, role=User.APP_MANAGER,
        )

    def analyze_as(self, user):
        user = User.objects.get(pk=user.pk)  # each real request loads the user fresh
        self.client.force_authenticate(user=user)
        with patch("apps.soil.views.analyze_soil_image", return_value=FAKE_SOIL):
            return self.client.post(
                reverse("soil-analyze"), {"image": _file(image_upload()[1])}, format="multipart"
            )

    # ------------------------------------------------------------ instructions

    def test_instructions_expose_prices_and_bank_details(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.get(reverse("payment-instructions"), {"currency": "XOF"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["currency"], "XOF")
        self.assertEqual(response.data["account"]["bank_name"], "Ecobank CI")
        prices = {p["plan"]: p["amount"] for p in response.data["plans"]}
        self.assertEqual(prices[Subscription.PRO], "15000.00")
        methods = {m["code"] for m in response.data["methods"]}
        self.assertEqual(methods, {"cash", "bank_transfer"})

    def test_unpriced_currency_lists_the_ones_that_work(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.get(reverse("payment-instructions"), {"currency": "KES"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["available_currencies"], ["NGN", "XOF"])

    # --------------------------------------------------------- bank transfer

    def test_farmer_declares_transfer_then_staff_confirms(self):
        self.assertEqual(self.analyze_as(self.farmer).status_code, 402)

        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.PRO, "method": "bank_transfer",
             "currency": "XOF", "amount": "15000", "reference": "ECO-99812"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        payment_id = response.data["payment"]["id"]
        self.assertEqual(response.data["payment"]["status"], Payment.PENDING)

        # declaring a payment does not by itself unlock anything
        self.assertEqual(self.analyze_as(self.farmer).status_code, 402)

        self.client.force_authenticate(user=self.staff)
        with sync_emails():
            response = self.client.post(reverse("payment-confirm", args=[payment_id]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["subscription"]["plan"], Subscription.PRO)

        self.assertEqual(self.analyze_as(self.farmer).status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Payment Confirmed", mail.outbox[0].subject)

    def test_transfer_needs_a_reference_or_a_receipt_photo(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.PRO, "method": "bank_transfer", "currency": "XOF"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("reference", response.data)

    def test_receipt_photo_stands_in_for_a_reference(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.PRO, "method": "bank_transfer",
             "currency": "XOF", "proof": _file(image_upload()[1])},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["payment"]["proof"])

    def test_underpayment_is_accepted_but_flagged_for_staff(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.PRO, "method": "bank_transfer",
             "currency": "XOF", "amount": "9000", "reference": "ECO-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["payment"]["expected_amount"], "15000.00")
        self.assertEqual(response.data["payment"]["shortfall"], "6000.00")

    def test_amount_defaults_to_the_list_price(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.BASIC, "method": "bank_transfer",
             "currency": "XOF", "reference": "ECO-2"},
            format="json",
        )
        self.assertEqual(response.data["payment"]["amount"], "5000.00")

    def test_multi_month_payment_is_priced_per_month(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.PRO, "months": 3, "method": "bank_transfer",
             "currency": "XOF", "reference": "ECO-3"},
            format="json",
        )
        self.assertEqual(response.data["payment"]["amount"], "45000.00")

        self.client.force_authenticate(user=self.staff)
        self.client.post(reverse("payment-confirm", args=[response.data["payment"]["id"]]))

        self.farmer.subscription.refresh_from_db()
        self.assertEqual(self.farmer.subscription.days_remaining, 90)

    def test_price_must_exist_in_the_requested_currency(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.BASIC, "method": "cash", "currency": "NGN"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("currency", response.data)

    # ----------------------------------------------------------------- cash

    def test_staff_recording_cash_activates_the_plan_on_the_spot(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("payment-list-create"),
            {"email": self.farmer.email, "plan": Subscription.PRO,
             "method": "cash", "currency": "XOF", "reference": "RC-0042"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment"]["status"], Payment.CONFIRMED)
        self.assertEqual(response.data["payment"]["recorded_by_email"], self.staff.email)

        self.assertEqual(self.analyze_as(self.farmer).status_code, 200)

    def test_farmer_cannot_record_a_payment_for_someone_else(self):
        victim = User.objects.create_user(
            username="v@example.com", email="v@example.com", password="x" * 12, role=User.FARMER,
        )
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("payment-list-create"),
            {"email": victim.email, "plan": Subscription.PRO,
             "method": "cash", "currency": "XOF"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Payment.objects.filter(user=victim).exists())

    # ------------------------------------------------------------- rejecting

    def test_rejecting_leaves_the_plan_untouched_and_tells_the_farmer(self):
        self.client.force_authenticate(user=self.farmer)
        payment_id = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.PRO, "method": "bank_transfer",
             "currency": "XOF", "reference": "FAKE-1"},
            format="json",
        ).data["payment"]["id"]

        self.client.force_authenticate(user=self.staff)
        with sync_emails():
            response = self.client.post(
                reverse("payment-reject", args=[payment_id]),
                {"reason": "No matching credit on the bank statement."},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["payment"]["status"], Payment.REJECTED)

        self.farmer.subscription.refresh_from_db()
        self.assertEqual(self.farmer.subscription.plan, Subscription.TRIAL)
        self.assertEqual(self.analyze_as(self.farmer).status_code, 402)
        self.assertIn("Could Not Be Verified", mail.outbox[0].subject)

    def test_confirmed_payment_cannot_be_rejected_afterwards(self):
        self.client.force_authenticate(user=self.staff)
        payment_id = self.client.post(
            reverse("payment-list-create"),
            {"email": self.farmer.email, "plan": Subscription.PRO,
             "method": "cash", "currency": "XOF"},
            format="json",
        ).data["payment"]["id"]

        response = self.client.post(reverse("payment-reject", args=[payment_id]))
        self.assertEqual(response.status_code, 400)

    def test_double_confirmation_is_refused(self):
        self.client.force_authenticate(user=self.farmer)
        payment_id = self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.PRO, "method": "bank_transfer",
             "currency": "XOF", "reference": "ECO-7"},
            format="json",
        ).data["payment"]["id"]

        self.client.force_authenticate(user=self.staff)
        self.assertEqual(self.client.post(reverse("payment-confirm", args=[payment_id])).status_code, 200)
        self.assertEqual(self.client.post(reverse("payment-confirm", args=[payment_id])).status_code, 400)

    # ------------------------------------------------------------------ list

    def test_farmers_only_see_their_own_payments(self):
        other = User.objects.create_user(
            username="o@example.com", email="o@example.com", password="x" * 12, role=User.FARMER,
        )
        Payment.objects.create(
            user=other, plan=Subscription.PRO, amount=15000, currency="XOF", method=Payment.CASH,
        )
        Payment.objects.create(
            user=self.farmer, plan=Subscription.PRO, amount=15000, currency="XOF", method=Payment.CASH,
        )

        self.client.force_authenticate(user=self.farmer)
        response = self.client.get(reverse("payment-list-create"))
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["user_email"], self.farmer.email)

        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("payment-list-create"), {"status": Payment.PENDING})
        self.assertEqual(len(response.data), 2)


class SeedPaymentConfigTests(TestCase):
    """The bootstrap command that makes a fresh deploy usable."""

    CONFIG = {
        "prices": [
            {"plan": "basic", "currency": "XOF", "amount": 5000},
            {"plan": "pro", "currency": "xof", "amount": 15000},
        ],
        "accounts": [{
            "currency": "XOF", "bank_name": "Ecobank CI",
            "account_name": "EasyAgric SARL", "account_number": "CI001",
            "cash_contact_phone": "+225 07 00 00 00",
        }],
    }

    def seed(self, payload=None, **options):
        out = StringIO()
        path = Path(self.tmp.name) / "config.json"
        path.write_text(json.dumps(self.CONFIG if payload is None else payload))
        call_command("seed_payment_config", file=str(path), stdout=out, **options)
        return out.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_seeds_prices_and_account(self):
        self.seed()

        self.assertEqual(PlanPrice.objects.count(), 2)
        self.assertEqual(PaymentAccount.objects.count(), 1)
        price = PlanPrice.lookup(Subscription.PRO, "XOF")
        self.assertEqual(price.amount, Decimal("15000"))  # lowercase currency normalised
        self.assertEqual(PaymentAccount.objects.get().bank_name, "Ecobank CI")

    def test_rerunning_is_idempotent_and_preserves_admin_edits(self):
        self.seed()
        # ops repriced from Django admin after launch
        PlanPrice.objects.filter(plan=Subscription.PRO).update(amount=Decimal("20000"))

        output = self.seed()

        self.assertEqual(PlanPrice.objects.count(), 2)
        self.assertEqual(PlanPrice.lookup(Subscription.PRO, "XOF").amount, Decimal("20000"))
        self.assertIn("inchangé", output)

    def test_overwrite_forces_the_json_values(self):
        self.seed()
        PlanPrice.objects.filter(plan=Subscription.PRO).update(amount=Decimal("20000"))

        self.seed(overwrite=True)

        self.assertEqual(PlanPrice.lookup(Subscription.PRO, "XOF").amount, Decimal("15000"))

    def test_no_config_is_a_silent_no_op(self):
        out = StringIO()
        call_command("seed_payment_config", stdout=out)

        self.assertFalse(PlanPrice.objects.exists())
        self.assertIn("étape ignorée", out.getvalue())

    def test_seeded_config_makes_the_payment_endpoints_work(self):
        self.seed()

        farmer = User.objects.create_user(
            username="s@example.com", email="s@example.com", password="x" * 12, role=User.FARMER,
        )
        client = APIClient()
        client.force_authenticate(user=farmer)

        response = client.get(reverse("payment-instructions"), {"currency": "XOF"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account"]["bank_name"], "Ecobank CI")
        self.assertEqual(len(response.data["plans"]), 2)

    # ------------------------------------------------------------- validation

    def test_free_trial_cannot_be_priced(self):
        payload = {"prices": [{"plan": "trial", "currency": "XOF", "amount": 100}]}
        with self.assertRaisesMessage(CommandError, "n'est pas un plan payant"):
            self.seed(payload)

    def test_unknown_currency_is_rejected(self):
        payload = {"prices": [{"plan": "pro", "currency": "ZZZ", "amount": 100}]}
        with self.assertRaisesMessage(CommandError, "devise 'ZZZ' inconnue"):
            self.seed(payload)

    def test_non_positive_amount_is_rejected(self):
        payload = {"prices": [{"plan": "pro", "currency": "XOF", "amount": 0}]}
        with self.assertRaisesMessage(CommandError, "supérieur à zéro"):
            self.seed(payload)

    def test_account_missing_bank_details_is_rejected(self):
        payload = {"accounts": [{"currency": "XOF", "bank_name": "Ecobank CI"}]}
        with self.assertRaisesMessage(CommandError, "account_name, account_number"):
            self.seed(payload)

    def test_bad_json_reports_clearly_instead_of_crashing(self):
        path = Path(self.tmp.name) / "broken.json"
        path.write_text("{not json")
        with self.assertRaisesMessage(CommandError, "JSON invalide"):
            call_command("seed_payment_config", file=str(path))

    def test_missing_file_is_reported(self):
        with self.assertRaisesMessage(CommandError, "Fichier introuvable"):
            call_command("seed_payment_config", file="/nope/missing.json")

    def test_shipped_example_file_is_valid_and_loadable(self):
        """The template we ask people to copy must actually work."""
        example = json.loads(Path("payment_config.example.json").read_text())
        example.pop("_comment", None)

        self.seed(example)

        self.assertEqual(PlanPrice.objects.count(), 2)
        self.assertEqual(PaymentAccount.objects.count(), 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FarmerUpgradeRequestTests(TestCase):
    """A farmer can ask to go paid, but only staff can make it take effect."""

    def setUp(self):
        self.client = APIClient()
        PlanPrice.objects.create(plan=Subscription.PRO, currency="XOF", amount=15000)
        PlanPrice.objects.create(plan=Subscription.BASIC, currency="XOF", amount=5000)
        PaymentAccount.objects.create(
            currency="XOF", bank_name="Ecobank CI",
            account_name="EasyAgric SARL", account_number="CI001",
        )
        self.farmer = User.objects.create_user(
            username="up@example.com", email="up@example.com", password="x" * 12, role=User.FARMER,
        )
        Subscription.start_trial(self.farmer)
        Subscription.objects.filter(user=self.farmer).update(analyses_used=5)
        self.staff = User.objects.create_user(
            username="mgr@example.com", email="mgr@example.com", password="x" * 12, role=User.APP_MANAGER,
        )

    def analyze_as(self, user):
        user = User.objects.get(pk=user.pk)
        self.client.force_authenticate(user=user)
        with patch("apps.soil.views.analyze_soil_image", return_value=FAKE_SOIL):
            return self.client.post(
                reverse("soil-analyze"), {"image": _file(image_upload()[1])}, format="multipart"
            )

    def request_upgrade(self, **overrides):
        self.client.force_authenticate(user=self.farmer)
        payload = {"plan": Subscription.PRO, "method": "cash", "currency": "XOF"}
        payload.update(overrides)
        return self.client.post(reverse("subscription-upgrade-request"), payload, format="json")

    # ------------------------------------------------------------ the request

    def test_request_needs_no_payment_reference_and_quotes_the_price(self):
        response = self.request_upgrade()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount_due"], Decimal("15000.00"))
        self.assertEqual(response.data["account"]["bank_name"], "Ecobank CI")
        self.assertEqual(response.data["payment"]["status"], Payment.PENDING)

    def test_requesting_does_not_activate_anything(self):
        self.request_upgrade()

        self.farmer.subscription.refresh_from_db()
        self.assertEqual(self.farmer.subscription.plan, Subscription.TRIAL)
        self.assertEqual(self.analyze_as(self.farmer).status_code, 402)

    def test_pending_request_is_visible_to_the_app(self):
        self.request_upgrade()

        self.client.force_authenticate(user=self.farmer)
        response = self.client.get(reverse("subscription-me"))
        self.assertEqual(response.data["plan"], Subscription.TRIAL)
        self.assertEqual(response.data["pending_upgrade"]["plan"], Subscription.PRO)
        self.assertEqual(response.data["pending_upgrade"]["status"], Payment.PENDING)

    def test_no_pending_upgrade_reads_as_null(self):
        self.client.force_authenticate(user=self.farmer)
        self.assertIsNone(self.client.get(reverse("subscription-me")).data["pending_upgrade"])

    # ------------------------------------------------------- staff confirms it

    def test_staff_confirmation_is_what_starts_the_plan(self):
        payment_id = self.request_upgrade().data["payment"]["id"]

        self.client.force_authenticate(user=self.staff)
        with sync_emails():
            response = self.client.post(reverse("payment-confirm", args=[payment_id]))
        self.assertEqual(response.status_code, 200, response.data)

        self.farmer.subscription.refresh_from_db()
        self.assertEqual(self.farmer.subscription.plan, Subscription.PRO)
        self.assertEqual(self.analyze_as(self.farmer).status_code, 200)
        self.assertIn("Payment Confirmed", mail.outbox[0].subject)

        # the request is no longer pending once acted on
        self.client.force_authenticate(user=self.farmer)
        self.assertIsNone(self.client.get(reverse("subscription-me")).data["pending_upgrade"])

    def test_farmer_cannot_confirm_their_own_request(self):
        payment_id = self.request_upgrade().data["payment"]["id"]

        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(reverse("payment-confirm", args=[payment_id]))

        self.assertEqual(response.status_code, 403)
        self.farmer.subscription.refresh_from_db()
        self.assertEqual(self.farmer.subscription.plan, Subscription.TRIAL)

    def test_farmer_cannot_reach_the_direct_upgrade_endpoint(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(
            reverse("subscription-upgrade"),
            {"email": self.farmer.email, "plan": Subscription.PRO},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------- changing my mind

    def test_new_request_supersedes_the_previous_intent(self):
        self.request_upgrade(plan=Subscription.BASIC)
        self.request_upgrade(plan=Subscription.PRO)

        pending = Payment.objects.filter(user=self.farmer, status=Payment.PENDING)
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.get().plan, Subscription.PRO)
        superseded = Payment.objects.get(plan=Subscription.BASIC)
        self.assertEqual(superseded.status, Payment.REJECTED)
        self.assertIn("Superseded", superseded.rejection_reason)

    def test_a_declared_payment_with_evidence_is_never_auto_superseded(self):
        self.client.force_authenticate(user=self.farmer)
        self.client.post(
            reverse("payment-list-create"),
            {"plan": Subscription.BASIC, "method": "bank_transfer",
             "currency": "XOF", "reference": "ECO-555"},
            format="json",
        )

        self.request_upgrade(plan=Subscription.PRO)

        # the referenced transfer still awaits a human decision
        declared = Payment.objects.get(reference="ECO-555")
        self.assertEqual(declared.status, Payment.PENDING)
        self.assertEqual(Payment.objects.filter(status=Payment.PENDING).count(), 2)

    # -------------------------------------------------------------- validation

    def test_cannot_request_the_free_trial(self):
        response = self.request_upgrade(plan=Subscription.TRIAL)
        self.assertEqual(response.status_code, 400)
        self.assertIn("plan", response.data)

    def test_cannot_request_a_currency_with_no_price(self):
        response = self.request_upgrade(currency="KES")
        self.assertEqual(response.status_code, 400)
        self.assertIn("currency", response.data)

    def test_staff_are_redirected_to_the_direct_upgrade_endpoint(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("subscription-upgrade-request"),
            {"plan": Subscription.PRO, "method": "cash", "currency": "XOF"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not metered", response.data["error"])
