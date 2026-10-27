from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import date

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.text import slugify

BOT_MARKERS = (
    "bot",
    "crawl",
    "spider",
    "slurp",
    "facebookexternalhit",
    "whatsapp",
    "preview",
    "headless",
    "lighthouse",
    "curl",
    "wget",
    "python-requests",
)


def is_bot(user_agent: str | None) -> bool:
    ua = (user_agent or "").lower()
    return not ua or any(marker in ua for marker in BOT_MARKERS)


def session_hash(session_key: str | None, day: date | None = None) -> str:
    """HMAC-SHA256 of the session key + date with a SECRET_KEY-derived salt (§5.10)."""
    day = day or timezone.localdate()
    salt = salted_hmac("kd.telemetry.salt", "session", algorithm="sha256").hexdigest()
    msg = f"{session_key or 'anon'}:{day.isoformat()}".encode()
    return hmac.new(salt.encode(), msg, hashlib.sha256).hexdigest()


def unique_slug(instance, value: str, field: str = "slug", max_length: int = 80) -> str:
    base = slugify(value)[: max_length - 9] or "item"
    model = type(instance)
    slug = base
    while model._default_manager.filter(**{field: slug}).exclude(pk=instance.pk).exists():
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


def random_filename(instance, filename: str, prefix: str = "uploads") -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    now = timezone.now()
    return f"{prefix}/{now:%Y/%m}/{uuid.uuid4().hex}.{ext}"


def get_client_ip(request) -> str:
    """Only used transiently (rate limits / GeoIP hint). Never stored."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded and getattr(settings, "AXES_IPWARE_PROXY_COUNT", 0):
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def absolute_url(path: str) -> str:
    return f"{settings.SITE_URL}{path}"
