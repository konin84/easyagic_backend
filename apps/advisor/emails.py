import logging
import threading

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

from apps.utils.email_translate import translate_email_content

logger = logging.getLogger(__name__)


def send_advice_email(user, advice: dict) -> None:
    """Fire-and-forget: sends the full advice report in a background thread."""
    thread = threading.Thread(target=_deliver, args=(user, advice), daemon=True)
    thread.start()


def _deliver(user, advice: dict) -> None:
    context = {
        "user": user,
        "soil": advice.get("soil_analysis") or {},
        "current_weather": (advice.get("weather") or {}).get("current_weather", {}),
        "current_soil": (advice.get("weather") or {}).get("current_soil", {}),
        "crop_recommendations": advice.get("crop_recommendations") or [],
    }
    subject = "EasyAgric — Your Farm Advice Report"
    text_body = render_to_string("emails/advice_report.txt", context)
    html_body = render_to_string("emails/advice_report.html", context)

    language = getattr(user, "language", "en")
    text_body = translate_email_content(text_body, language, is_html=False)
    html_body = translate_email_content(html_body, language, is_html=True)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send()
    except Exception:
        logger.exception("Failed to send advice email to %s", user.email)
