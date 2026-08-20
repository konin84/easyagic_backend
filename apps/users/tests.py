from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.history.models import AnalysisRecord
from apps.notifications.models import DeviceToken
from apps.subscriptions.models import Payment, PlanPrice, Subscription

from .models import User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AdminUserManagementTests(TestCase):
    """Platform admins deleting and deactivating accounts."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="root@example.com", email="root@example.com",
            password="x" * 12, role=User.ADMIN,
        )
        self.farmer = User.objects.create_user(
            username="f@example.com", email="f@example.com",
            password="x" * 12, role=User.FARMER,
        )
        Subscription.start_trial(self.farmer)
        self.manager = User.objects.create_user(
            username="m@example.com", email="m@example.com",
            password="x" * 12, role=User.APP_MANAGER,
        )
        self.client.force_authenticate(user=self.admin)

    def detail_url(self, user):
        return reverse("admin-user-detail", args=[user.pk])

    # ------------------------------------------------------------ permissions

    def test_app_manager_cannot_delete_users(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(self.detail_url(self.farmer))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.farmer.pk).exists())

    def test_farmer_cannot_delete_users(self):
        self.client.force_authenticate(user=self.farmer)
        self.assertEqual(self.client.delete(self.detail_url(self.manager)).status_code, 403)

    def test_anonymous_cannot_delete_users(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.delete(self.detail_url(self.farmer)).status_code, 401)

    # --------------------------------------------------------------- deleting

    def test_admin_deletes_a_farmer_and_their_data(self):
        AnalysisRecord.objects.create(farmer=self.farmer, soil_analysis={"soil_type": "Loam"})
        DeviceToken.objects.create(user=self.farmer, token="tok-1", platform="android")

        response = self.client.delete(self.detail_url(self.farmer))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(User.objects.filter(pk=self.farmer.pk).exists())
        self.assertEqual(AnalysisRecord.objects.count(), 0)
        self.assertEqual(DeviceToken.objects.count(), 0)
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertEqual(response.data["deleted"]["history.AnalysisRecord"], 1)

    def test_admin_can_delete_an_app_manager(self):
        self.assertEqual(self.client.delete(self.detail_url(self.manager)).status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.manager.pk).exists())

    def test_deleting_a_missing_user_is_404(self):
        self.assertEqual(self.client.delete(reverse("admin-user-detail", args=[999999])).status_code, 404)

    # ------------------------------------------------------------- guardrails

    def test_admin_cannot_delete_themselves(self):
        response = self.client.delete(self.detail_url(self.admin))

        self.assertEqual(response.status_code, 400)
        self.assertIn("your own account", response.data["error"])
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_an_admin_always_survives_a_deletion_spree(self):
        """
        Refusing self-deletion is what keeps the platform from being locked out:
        whoever is doing the deleting cannot remove themselves.
        """
        second = User.objects.create_superuser(
            username="two@example.com", email="two@example.com",
            password="x" * 12, role=User.ADMIN,
        )

        self.client.force_authenticate(user=second)
        self.assertEqual(self.client.delete(self.detail_url(self.admin)).status_code, 200)
        self.assertEqual(self.client.delete(self.detail_url(second)).status_code, 400)

        # the deleter is still standing, so the platform keeps an admin
        remaining = User.objects.filter(role=User.ADMIN, is_active=True)
        self.assertTrue(remaining.exists())
        self.assertIn(second.email, [u.email for u in remaining])

    def test_deleting_a_farmer_with_confirmed_payments_is_refused_by_default(self):
        PlanPrice.objects.create(plan=Subscription.PRO, currency="XOF", amount=15000)
        Payment.objects.create(
            user=self.farmer, plan=Subscription.PRO, amount=15000,
            currency="XOF", method=Payment.CASH, status=Payment.CONFIRMED,
        )

        response = self.client.delete(self.detail_url(self.farmer))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["confirmed_payments"], 1)
        self.assertIn("Deactivate", response.data["hint"])
        self.assertTrue(User.objects.filter(pk=self.farmer.pk).exists())

    def test_force_deletes_despite_confirmed_payments(self):
        Payment.objects.create(
            user=self.farmer, plan=Subscription.PRO, amount=15000,
            currency="XOF", method=Payment.CASH, status=Payment.CONFIRMED,
        )

        response = self.client.delete(self.detail_url(self.farmer) + "?force=true")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.farmer.pk).exists())
        self.assertEqual(Payment.objects.count(), 0)

    def test_pending_payments_do_not_block_deletion(self):
        Payment.objects.create(
            user=self.farmer, plan=Subscription.PRO, amount=15000,
            currency="XOF", method=Payment.CASH, status=Payment.PENDING,
        )
        self.assertEqual(self.client.delete(self.detail_url(self.farmer)).status_code, 200)

    def test_staff_who_reviewed_a_payment_can_be_deleted_without_losing_it(self):
        payment = Payment.objects.create(
            user=self.farmer, plan=Subscription.PRO, amount=15000, currency="XOF",
            method=Payment.CASH, status=Payment.CONFIRMED,
            recorded_by=self.manager, reviewed_by=self.manager,
        )

        self.assertEqual(self.client.delete(self.detail_url(self.manager)).status_code, 200)

        payment.refresh_from_db()
        self.assertIsNone(payment.recorded_by)
        self.assertIsNone(payment.reviewed_by)
        self.assertEqual(payment.status, Payment.CONFIRMED)

    # ---------------------------------------------------------- preview + list

    def test_preview_reports_what_deletion_would_destroy(self):
        AnalysisRecord.objects.create(farmer=self.farmer, soil_analysis={})
        AnalysisRecord.objects.create(farmer=self.farmer, soil_analysis={})

        response = self.client.get(self.detail_url(self.farmer))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], self.farmer.email)
        self.assertEqual(response.data["deletion_impact"]["history.AnalysisRecord"], 2)
        self.assertEqual(response.data["deletion_impact"]["subscriptions.Subscription"], 1)

    def test_list_filters_by_role_and_search(self):
        response = self.client.get(reverse("admin-user-list"), {"role": User.FARMER})
        self.assertEqual([u["email"] for u in response.data["results"]], [self.farmer.email])
        self.assertEqual(response.data["count"], 1)

        response = self.client.get(reverse("admin-user-list"), {"search": "m@ex"})
        self.assertEqual([u["email"] for u in response.data["results"]], [self.manager.email])

    def test_list_exposes_the_ids_needed_for_deletion(self):
        response = self.client.get(reverse("admin-user-list"), {"role": User.FARMER})

        row = response.data["results"][0]
        self.assertEqual(row["id"], self.farmer.pk)
        self.assertEqual(row["plan"], Subscription.TRIAL)
        self.assertTrue(row["is_active"])

    def test_search_also_matches_farm_name(self):
        self.farmer.farm_name = "Koffi Cocoa Estate"
        self.farmer.save(update_fields=["farm_name"])

        response = self.client.get(reverse("admin-user-list"), {"search": "cocoa"})
        self.assertEqual([u["email"] for u in response.data["results"]], [self.farmer.email])

    def test_count_reports_the_full_total_beyond_the_page(self):
        for i in range(8):
            User.objects.create_user(
                username=f"bulk{i}@example.com", email=f"bulk{i}@example.com",
                password="x" * 12, role=User.FARMER,
            )

        response = self.client.get(reverse("admin-user-list"), {"role": User.FARMER, "limit": 3})

        self.assertEqual(response.data["count"], 9)      # 8 + the one from setUp
        self.assertEqual(len(response.data["results"]), 3)
        self.assertEqual(response.data["limit"], 3)

    def test_offset_walks_through_the_pages(self):
        for i in range(4):
            User.objects.create_user(
                username=f"p{i}@example.com", email=f"p{i}@example.com",
                password="x" * 12, role=User.FARMER,
            )

        first = self.client.get(reverse("admin-user-list"), {"role": User.FARMER, "limit": 2})
        second = self.client.get(
            reverse("admin-user-list"), {"role": User.FARMER, "limit": 2, "offset": 2}
        )

        ids_a = [u["id"] for u in first.data["results"]]
        ids_b = [u["id"] for u in second.data["results"]]
        self.assertEqual(len(ids_a), 2)
        self.assertEqual(len(ids_b), 2)
        self.assertFalse(set(ids_a) & set(ids_b), "pages must not overlap")

    def test_limit_is_capped(self):
        response = self.client.get(reverse("admin-user-list"), {"limit": 99999})
        self.assertEqual(response.data["limit"], 500)

    def test_bad_paging_values_are_rejected(self):
        response = self.client.get(reverse("admin-user-list"), {"limit": "many"})
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------ deactivating

    def test_deactivate_keeps_the_account_and_blocks_login(self):
        response = self.client.patch(
            self.detail_url(self.farmer), {"is_active": False}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.farmer.refresh_from_db()
        self.assertFalse(self.farmer.is_active)
        self.assertTrue(User.objects.filter(pk=self.farmer.pk).exists())

        login = APIClient().post(
            reverse("auth-login"),
            {"email": self.farmer.email, "password": "x" * 12},
            format="json",
        )
        self.assertEqual(login.status_code, 400)

    def test_reactivate_restores_access(self):
        self.client.patch(self.detail_url(self.farmer), {"is_active": False}, format="json")
        self.client.patch(self.detail_url(self.farmer), {"is_active": True}, format="json")

        self.farmer.refresh_from_db()
        self.assertTrue(self.farmer.is_active)

    def test_admin_cannot_deactivate_themselves(self):
        response = self.client.patch(
            self.detail_url(self.admin), {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_patch_without_is_active_is_rejected(self):
        response = self.client.patch(self.detail_url(self.farmer), {}, format="json")
        self.assertEqual(response.status_code, 400)
