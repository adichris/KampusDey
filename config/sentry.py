"""Sentry error and performance monitoring, set up from environment variables.

Privacy (AGENTS.md): no IP addresses, cookies or personal details are sent. Only errors,
stack traces and a small sample of request timings.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Keys whose values are replaced before an event leaves the server (on top of Sentry's own
# defaults such as password, secret, token, api_key, authorization, cookie, session).
EXTRA_DENYLIST = [
    "phone",
    "whatsapp",
    "telegram",
    "email",
    "guest_key",
    "guest_email",
    "document",
    "proof",
    "otp",
    "code_hash",
    "remote_addr",
    "ip_address",
    "x_forwarded_for",
    "x_real_ip",
]

# Expected noise that is not worth an alert.
IGNORE_ERRORS = [
    "django.core.exceptions.DisallowedHost",
    "django_ratelimit.exceptions.Ratelimited",
]


def git_release(base_dir: Path) -> str | None:
    """Short commit hash of the deployed checkout, used as the Sentry release."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"kampusdey@{sha}" if sha else None


def strip_personal_data(event, hint):
    """Last line of defence: drop IPs, cookies and user details from every event."""
    request = event.get("request") or {}
    request.pop("cookies", None)
    env = request.get("env") or {}
    for key in ("REMOTE_ADDR", "SERVER_NAME"):
        env.pop(key, None)
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in ("cookie", "x-forwarded-for", "x-real-ip", "authorization"):
            headers.pop(key, None)
    user = event.get("user")
    if user:
        # keep only the numeric id so an error can be linked to an account in the admin
        event["user"] = {"id": user["id"]} if user.get("id") else {}
    return event


def init(dsn: str, *, environment: str, base_dir: Path, release: str = "", traces: float = 0.05):
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or git_release(base_dir),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=traces,
        send_default_pii=False,
        include_local_variables=False,  # locals can hold form data and phone numbers
        max_request_body_size="never",
        event_scrubber=EventScrubber(denylist=DEFAULT_DENYLIST + EXTRA_DENYLIST, recursive=True),
        before_send=strip_personal_data,
        ignore_errors=IGNORE_ERRORS,
    )
    return True
