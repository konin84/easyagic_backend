import logging
import threading

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

from apps.utils.email_translate import translate_email_content

logger = logging.getLogger(__name__)


def send_welcome_email(user, password: str) -> None:
    context = {"user": user, "password": password}
    text_body = render_to_string("emails/welcome.txt", context)
    html_body = render_to_string("emails/welcome.html", context)
    _send_async("Welcome to EasyAgric — Your Login Details", text_body, html_body, user.email, user.language)


def send_otp_email(user, otp_code: str) -> None:
    context = {"user": user, "otp_code": otp_code}
    text_body = render_to_string("emails/otp.txt", context)
    html_body = render_to_string("emails/otp.html", context)
    _send_async("EasyAgric — Your Password Reset Code", text_body, html_body, user.email, user.language)


def _send_async(subject: str, text_body: str, html_body: str, recipient: str, language: str = "en") -> None:
    thread = threading.Thread(
        target=_deliver,
        args=(subject, text_body, html_body, recipient, language),
        daemon=True,
    )
    thread.start()


def _deliver(subject: str, text_body: str, html_body: str, recipient: str, language: str) -> None:
    translated_text = translate_email_content(text_body, language, is_html=False)
    translated_html = translate_email_content(html_body, language, is_html=True)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=translated_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    msg.attach_alternative(translated_html, "text/html")
    try:
        msg.send()
    except Exception:
        logger.exception("Failed to send email to %s", recipient)
