import json
import logging
import threading

from django.conf import settings
from django.db import connection

from apps.utils.email_translate import translate_batch

logger = logging.getLogger(__name__)

_firebase_app = None
_firebase_lock = threading.Lock()


def _get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    with _firebase_lock:
        if _firebase_app is not None:
            return _firebase_app

        credentials_json = getattr(settings, "FIREBASE_CREDENTIALS_JSON", None)
        if not credentials_json:
            return None

        try:
            import firebase_admin
            from firebase_admin import credentials

            cred = credentials.Certificate(json.loads(credentials_json))
            _firebase_app = firebase_admin.initialize_app(cred)
        except Exception:
            logger.exception("Failed to initialize Firebase app")

    return _firebase_app


def send_push(
    tokens: list[str],
    title: str,
    body: str,
    data: dict | None = None,
    language: str = "en",
) -> None:
    """Fire-and-forget push notification to a list of FCM tokens.

    `title` and `body` are written in English and translated to `language`
    before delivery. `data` is a routing payload and is never translated.
    """
    if not tokens:
        return
    threading.Thread(
        target=_deliver, args=(tokens, title, body, data or {}, language), daemon=True
    ).start()


def send_push_to_user(user, title: str, body: str, data: dict | None = None) -> None:
    """Push to every device registered by `user`, in that user's language."""
    tokens = list(user.device_tokens.values_list("token", flat=True))
    send_push(tokens, title, body, data, language=user.language)


def _deliver(tokens: list[str], title: str, body: str, data: dict, language: str) -> None:
    app = _get_firebase_app()
    if app is None:
        logger.warning("Firebase not configured — skipping push notification.")
        return

    try:
        from firebase_admin import messaging

        # One API call for both strings; falls back to English on failure.
        title, body = translate_batch([title, body], language)

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
        )
        response = messaging.send_each_for_multicast(message)
        if response.failure_count:
            logger.warning("Push: %d/%d failed", response.failure_count, len(tokens))
            _prune_dead_tokens(tokens, response.responses, messaging)
    except Exception:
        logger.exception("Failed to send push notification")
    finally:
        # This runs in its own thread, so Django opened a connection for it.
        connection.close()


def _prune_dead_tokens(tokens: list[str], responses: list, messaging) -> None:
    """Delete tokens FCM reports as permanently undeliverable."""
    from .models import DeviceToken

    permanent = (messaging.UnregisteredError, messaging.SenderIdMismatchError)
    dead = [
        token
        for token, result in zip(tokens, responses)
        if not result.success and isinstance(result.exception, permanent)
    ]
    if not dead:
        return

    deleted, _ = DeviceToken.objects.filter(token__in=dead).delete()
    logger.info("Push: pruned %d dead device token(s)", deleted)
