"""Email backend that follows the admin settings (Integrations → Email)."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend


def smtp_from_admin() -> dict | None:
    from apps.sitesettings.models import IntegrationSettings

    integ = IntegrationSettings.get_cached()
    if not integ.smtp_host:
        return None
    return {
        "host": integ.smtp_host,
        "port": integ.smtp_port,
        "username": integ.smtp_username,
        "password": integ.smtp_password,
        "use_tls": integ.smtp_use_tls and not integ.smtp_use_ssl,
        "use_ssl": integ.smtp_use_ssl,
        "from": integ.email_from,
    }


class ConfiguredEmailBackend(BaseEmailBackend):
    """SMTP from the admin when a host is set there, else EMAIL_FALLBACK_BACKEND."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.admin = smtp_from_admin()
        if self.admin:
            options = {k: v for k, v in self.admin.items() if k != "from"}
            self.inner = get_connection(
                "django.core.mail.backends.smtp.EmailBackend",
                fail_silently=fail_silently,
                timeout=20,
                **options,
            )
        else:
            self.inner = get_connection(
                settings.EMAIL_FALLBACK_BACKEND, fail_silently=fail_silently, **kwargs
            )

    def open(self):
        return self.inner.open()

    def close(self):
        return self.inner.close()

    def send_messages(self, email_messages):
        sender = self.admin and self.admin.get("from")
        if sender:
            for message in email_messages:
                if message.from_email in (settings.DEFAULT_FROM_EMAIL, None, ""):
                    message.from_email = sender
        return self.inner.send_messages(email_messages)
