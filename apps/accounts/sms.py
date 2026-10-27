"""SMS backends. Selected at runtime from IntegrationSettings.sms_provider (§6.2)."""

from __future__ import annotations

import logging

from apps.sitesettings.models import IntegrationSettings

logger = logging.getLogger("kampusdey.sms")


class SMSBackend:
    name = "base"

    def __init__(self, settings_obj: IntegrationSettings | None = None):
        self.settings = settings_obj or IntegrationSettings.get_cached()

    def send(self, to: str, message: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class NullSMSBackend(SMSBackend):
    name = "none"

    def send(self, to, message):
        logger.warning("SMS provider is 'none'; message to %s not sent", to[-4:])
        return False


class ConsoleSMSBackend(SMSBackend):
    """Development backend: prints the message (including OTP codes) to the console."""

    name = "console"
    outbox: list[tuple[str, str]] = []

    def send(self, to, message):
        ConsoleSMSBackend.outbox.append((to, message))
        print(f"[SMS to {to}] {message}")  # noqa: T201 - intended console output
        logger.info("SMS to %s: %s", to, message)
        return True


class _ProviderStub(SMSBackend):
    """Adapter stub. Production integrations are out of scope for this build (§12)."""

    def send(self, to, message):
        if not self.settings.sms_api_key:
            logger.error("%s selected but no API key is set", self.name)
            return False
        logger.error("%s adapter is a stub; implement send() before enabling it", self.name)
        return False


class HubtelSMSBackend(_ProviderStub):
    name = "hubtel"


class ArkeselSMSBackend(_ProviderStub):
    name = "arkesel"


class MNotifySMSBackend(_ProviderStub):
    name = "mnotify"


class OtherSMSBackend(_ProviderStub):
    name = "other"


BACKENDS = {
    b.name: b
    for b in [
        NullSMSBackend,
        ConsoleSMSBackend,
        HubtelSMSBackend,
        ArkeselSMSBackend,
        MNotifySMSBackend,
        OtherSMSBackend,
    ]
}


def get_sms_backend() -> SMSBackend:
    integ = IntegrationSettings.get_cached()
    return BACKENDS.get(integ.sms_provider, ConsoleSMSBackend)(integ)
