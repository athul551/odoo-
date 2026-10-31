from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

# --- fail fast when the deployment would silently swallow customer email.
# The spec promises a reset link at the customer's address and a sent invoice;
# Django's console backend writes both to stdout and reports success, so
# ``sent_at`` would claim a delivery that never happened. Refuse to boot.
if "console" in EMAIL_BACKEND:  # noqa: F405
    raise ImproperlyConfigured(
        "EMAIL_BACKEND is the console backend, which discards password-reset "
        "links and invoices instead of delivering them. Configure SMTP "
        "(EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend plus "
        "EMAIL_HOST/EMAIL_PORT/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD)."
    )
