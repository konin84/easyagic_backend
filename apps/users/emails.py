import logging
import threading

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


def send_welcome_email(user, password: str) -> None:
    context = {"user": user, "password": password}
    subject = "Welcome to EasyAgric — Your Login Details"
    text_body = render_to_string("emails/welcome.txt", context)
    html_body = render_to_string("emails/welcome.html", context)
    _send_async(subject, text_body, html_body, user.email)


def send_otp_email(user, otp_code: str) -> None:
    context = {"user": user, "otp_code": otp_code}
    subject = "EasyAgric — Your Password Reset Code"
    text_body = render_to_string("emails/otp.txt", context)
    html_body = render_to_string("emails/otp.html", context)
    _send_async(subject, text_body, html_body, user.email)


def _send_async(subject: str, text_body: str, html_body: str, recipient: str) -> None:
    thread = threading.Thread(target=_deliver, args=(subject, text_body, html_body, recipient), daemon=True)
    thread.start()


def _deliver(subject: str, text_body: str, html_body: str, recipient: str) -> None:
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send()
    except Exception:
        logger.exception("Failed to send email to %s", recipient)
