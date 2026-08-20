from django.template.loader import render_to_string

from apps.users.emails import _send_async


def send_payment_confirmed_email(payment):
    """Tell the farmer their money landed and the plan is live."""
    subscription = payment.user.subscription
    context = {"user": payment.user, "payment": payment, "subscription": subscription}
    _send_async(
        "EasyAgric — Payment Confirmed",
        render_to_string("emails/payment_confirmed.txt", context),
        render_to_string("emails/payment_confirmed.html", context),
        payment.user.email,
        payment.user.language,
    )


def send_payment_rejected_email(payment):
    context = {"user": payment.user, "payment": payment}
    _send_async(
        "EasyAgric — Payment Could Not Be Verified",
        render_to_string("emails/payment_rejected.txt", context),
        render_to_string("emails/payment_rejected.html", context),
        payment.user.email,
        payment.user.language,
    )
