from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.users.models import User

from .models import DeviceToken
from .services import _deliver, send_push_to_user


class FakeUnregisteredError(Exception):
    pass


class FakeSenderIdMismatchError(Exception):
    pass


class FakeQuotaExceededError(Exception):
    pass


def fake_messaging(responses):
    """Stand-in for firebase_admin.messaging with a scripted multicast result."""
    return SimpleNamespace(
        UnregisteredError=FakeUnregisteredError,
        SenderIdMismatchError=FakeSenderIdMismatchError,
        Notification=lambda **kw: SimpleNamespace(**kw),
        MulticastMessage=lambda **kw: SimpleNamespace(**kw),
        send_each_for_multicast=lambda msg: SimpleNamespace(
            failure_count=sum(1 for r in responses if not r.success),
            responses=responses,
        ),
    )


def ok():
    return SimpleNamespace(success=True, exception=None)


def failed(exc):
    return SimpleNamespace(success=False, exception=exc)


class PushDeliveryTests(TestCase):
    """_deliver translates the copy and prunes tokens FCM rejects for good."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="f@example.com", email="f@example.com",
            password="x" * 12, role=User.FARMER, language=User.FR,
        )
        for token in ("live", "dead", "wrong-sender", "throttled"):
            DeviceToken.objects.create(user=self.user, token=token, platform="android")

    def deliver(self, tokens, responses, language="en"):
        messaging = fake_messaging(responses)
        sent = {}
        with patch("apps.notifications.services._get_firebase_app", return_value=object()), \
             patch.dict("sys.modules", {"firebase_admin": SimpleNamespace(messaging=messaging)}):
            messaging.MulticastMessage = lambda **kw: sent.update(kw) or SimpleNamespace(**kw)
            _deliver(tokens, "Farm Analysis Ready", "Your Loam analysis is complete.", {}, language)
        return sent

    # ------------------------------------------------------------- pruning

    def test_unregistered_and_mismatched_tokens_are_deleted(self):
        self.deliver(
            ["live", "dead", "wrong-sender"],
            [ok(), failed(FakeUnregisteredError()), failed(FakeSenderIdMismatchError())],
        )

        self.assertEqual(
            set(DeviceToken.objects.values_list("token", flat=True)),
            {"live", "throttled"},
        )

    def test_transient_failures_keep_the_token(self):
        self.deliver(["live", "throttled"], [ok(), failed(FakeQuotaExceededError())])

        self.assertEqual(DeviceToken.objects.count(), 4)

    def test_full_success_deletes_nothing(self):
        self.deliver(["live", "dead"], [ok(), ok()])

        self.assertEqual(DeviceToken.objects.count(), 4)

    # --------------------------------------------------------- translation

    def test_copy_is_translated_before_sending(self):
        with patch(
            "apps.notifications.services.translate_batch",
            return_value=["Analyse prête", "Votre analyse Loam est terminée."],
        ) as translate:
            sent = self.deliver(["live"], [ok()], language="fr")

        translate.assert_called_once_with(
            ["Farm Analysis Ready", "Your Loam analysis is complete."], "fr"
        )
        self.assertEqual(sent["notification"].title, "Analyse prête")
        self.assertEqual(sent["notification"].body, "Votre analyse Loam est terminée.")

    def test_english_skips_the_translation_call(self):
        with patch("apps.notifications.services.translate_batch") as translate:
            sent = self.deliver(["live"], [ok()], language="en")

        translate.assert_not_called()
        self.assertEqual(sent["notification"].title, "Farm Analysis Ready")

    def test_routing_data_is_never_translated(self):
        messaging = fake_messaging([ok()])
        sent = {}
        with patch("apps.notifications.services._get_firebase_app", return_value=object()), \
             patch(
                 "apps.notifications.services.translate_batch",
                 return_value=["Titre", "Corps"],
             ) as translate, \
             patch.dict("sys.modules", {"firebase_admin": SimpleNamespace(messaging=messaging)}):
            messaging.MulticastMessage = lambda **kw: sent.update(kw) or SimpleNamespace(**kw)
            _deliver(["live"], "Title", "Body", {"type": "analysis_complete"}, "fr")

        # Only the copy goes to the translator; the routing key travels as-is.
        translate.assert_called_once_with(["Title", "Body"], "fr")
        self.assertEqual(sent["data"], {"type": "analysis_complete"})


class SendPushToUserTests(TestCase):
    """send_push_to_user gathers the user's tokens and their language."""

    def test_uses_the_users_own_tokens_and_language(self):
        user = User.objects.create_user(
            username="a@example.com", email="a@example.com",
            password="x" * 12, role=User.FARMER, language=User.SW,
        )
        other = User.objects.create_user(
            username="b@example.com", email="b@example.com",
            password="x" * 12, role=User.FARMER,
        )
        DeviceToken.objects.create(user=user, token="mine", platform="ios")
        DeviceToken.objects.create(user=other, token="theirs", platform="android")

        with patch("apps.notifications.services.send_push") as send_push:
            send_push_to_user(user, "Title", "Body", {"type": "x"})

        send_push.assert_called_once_with(
            ["mine"], "Title", "Body", {"type": "x"}, language="sw"
        )

    def test_user_without_devices_sends_nothing(self):
        user = User.objects.create_user(
            username="c@example.com", email="c@example.com",
            password="x" * 12, role=User.FARMER,
        )

        with patch("apps.notifications.services.threading.Thread") as thread:
            send_push_to_user(user, "Title", "Body")

        thread.assert_not_called()
