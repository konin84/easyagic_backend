import json
import logging
import threading

from django.conf import settings

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


def send_push(tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
    """Fire-and-forget push notification to a list of FCM tokens."""
    if not tokens:
        return
    threading.Thread(target=_deliver, args=(tokens, title, body, data or {}), daemon=True).start()


def _deliver(tokens: list[str], title: str, body: str, data: dict) -> None:
    app = _get_firebase_app()
    if app is None:
        logger.warning("Firebase not configured — skipping push notification.")
        return

    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
        )
        response = messaging.send_each_for_multicast(message)
        if response.failure_count:
            logger.warning("Push: %d/%d failed", response.failure_count, len(tokens))
    except Exception:
        logger.exception("Failed to send push notification")
