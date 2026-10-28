from __future__ import annotations

from django.core.mail import send_mail
from django.db.models import Q
from django.utils.translation import gettext as _

from apps.listings.sections import SECTIONS

from .models import SectionAvailability


def section_enabled(section: str, campus=None) -> bool:
    """Resolution: campus row → global row → registry default (all on, trips off)."""
    if section not in SECTIONS:
        return False
    scope = Q(campus__isnull=True) | (Q(campus=campus) if campus else Q(pk__in=[]))
    rows = {
        row.campus_id: row.enabled
        for row in SectionAvailability.objects.filter(scope, section=section)
    }
    if campus is not None and campus.pk in rows:
        return rows[campus.pk]
    if None in rows:
        return rows[None]
    return SECTIONS[section].default_enabled


def enabled_sections(campus=None) -> list:
    scope = Q(campus__isnull=True) | (Q(campus=campus) if campus else Q(pk__in=[]))
    rows = list(SectionAvailability.objects.filter(scope))
    global_rows = {r.section: r.enabled for r in rows if r.campus_id is None}
    campus_rows = {
        r.section: r.enabled for r in rows if campus is not None and r.campus_id == campus.pk
    }
    result = []
    for slug, section in SECTIONS.items():
        if slug in campus_rows:
            on = campus_rows[slug]
        elif slug in global_rows:
            on = global_rows[slug]
        else:
            on = section.default_enabled
        if on:
            result.append(section)
    return result


def enabled_section_slugs(campus=None) -> set[str]:
    return {s.slug for s in enabled_sections(campus)}


def send_test_email(to: str) -> int:
    return send_mail(
        _("KampusDey test email"),
        _("If you can read this, outgoing email works."),
        None,
        [to],
    )


def send_test_sms(to: str) -> bool:
    from apps.accounts.sms import get_sms_backend

    return get_sms_backend().send(to, _("KampusDey test SMS"))


def smtp_status() -> dict:
    from django.conf import settings

    from apps.core.mail import smtp_from_admin

    admin = smtp_from_admin()
    if admin:
        return {
            "source": "admin",
            "backend": "SMTP",
            "host": admin["host"],
            "port": admin["port"],
            "tls": admin["use_tls"] or admin["use_ssl"],
            "user_set": bool(admin["username"]),
            "from": admin["from"] or settings.DEFAULT_FROM_EMAIL,
        }
    backend = settings.EMAIL_FALLBACK_BACKEND.rsplit(".", 1)[-1]
    return {
        "source": "env",
        "backend": backend,
        "host": settings.EMAIL_HOST,
        "port": settings.EMAIL_PORT,
        "tls": settings.EMAIL_USE_TLS,
        "user_set": bool(settings.EMAIL_HOST_USER),
        "from": settings.DEFAULT_FROM_EMAIL,
        "sends_real_mail": "smtp" in settings.EMAIL_FALLBACK_BACKEND,
    }


def storage_status() -> dict:
    from django.conf import settings

    from apps.core.storage import s3_config

    public, private = s3_config(), s3_config(private=True)
    from .models import IntegrationSettings

    source = "admin" if IntegrationSettings.get_cached().s3_bucket else "env"
    return {
        "public": "s3" if public else "local",
        "private": "s3" if private else "local",
        "source": source if public else "",
        "bucket": public["bucket_name"] if public else "",
        "domain": (public or {}).get("custom_domain") or "",
        "media_root": str(settings.MEDIA_ROOT),
        "private_root": str(settings.PRIVATE_MEDIA_ROOT),
        "serve_media": settings.SERVE_MEDIA,
    }


def google_status() -> dict:
    from django.conf import settings

    from .models import IntegrationSettings

    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        return {"enabled": True, "source": "env"}
    integ = IntegrationSettings.get_cached()
    return {
        "enabled": bool(integ.google_client_id and integ.google_client_secret),
        "source": "admin",
    }


def sync_google_app(integ) -> None:
    """Mirror the admin's Google keys into allauth's SocialApp (env keys take priority)."""
    from allauth.socialaccount.models import SocialApp
    from django.conf import settings
    from django.contrib.sites.models import Site

    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        return  # configured in settings; a DB app as well would make allauth ambiguous
    apps = SocialApp.objects.filter(provider="google")
    if not (integ.google_client_id and integ.google_client_secret):
        apps.delete()
        return
    app = apps.first() or SocialApp(provider="google", name="Google")
    app.client_id = integ.google_client_id
    app.secret = integ.google_client_secret
    app.save()
    app.sites.add(Site.objects.get_current())


def runtime_status() -> dict:
    from django.conf import settings

    return {
        "debug": settings.DEBUG,
        "redis": bool(settings.REDIS_URL),
        "celery_eager": bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)),
        "sentry": bool(getattr(settings, "SENTRY_DSN", "")),
        "staff_mfa": settings.STAFF_MFA_REQUIRED,
        "site_url": settings.SITE_URL,
        "database": settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1],
    }
