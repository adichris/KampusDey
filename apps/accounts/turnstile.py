"""Cloudflare Turnstile server-side verification (only when keys are set)."""

from __future__ import annotations

import logging

import requests
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.sitesettings.models import IntegrationSettings

logger = logging.getLogger(__name__)
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_enabled() -> bool:
    integ = IntegrationSettings.get_cached()
    return bool(integ.turnstile_site_key and integ.turnstile_secret)


def verify_token(token: str, remote_ip: str = "") -> bool:
    integ = IntegrationSettings.get_cached()
    if not (integ.turnstile_site_key and integ.turnstile_secret):
        return True
    if not token:
        return False
    try:
        resp = requests.post(
            VERIFY_URL,
            data={"secret": integ.turnstile_secret, "response": token, "remoteip": remote_ip},
            timeout=8,
        )
        return bool(resp.json().get("success"))
    except (requests.RequestException, ValueError):
        logger.warning("Turnstile verification failed to complete")
        return False


class TurnstileMixin:
    """Form mixin: validates `cf-turnstile-response` when Turnstile is configured."""

    turnstile_error = _("Please complete the security check.")

    def clean(self):
        cleaned = super().clean()
        if turnstile_enabled():
            request = getattr(self, "request", None)
            token = request.POST.get("cf-turnstile-response", "") if request else ""
            from apps.core.utils import get_client_ip

            if not verify_token(token, get_client_ip(request) if request else ""):
                raise forms.ValidationError(self.turnstile_error)
        return cleaned
