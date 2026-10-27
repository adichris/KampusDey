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
    campus_rows = {r.section: r.enabled for r in rows if campus is not None and r.campus_id == campus.pk}
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

    return {
        "backend": settings.EMAIL_BACKEND.rsplit(".", 1)[-1],
        "host": settings.EMAIL_HOST,
        "port": settings.EMAIL_PORT,
        "tls": settings.EMAIL_USE_TLS,
        "user_set": bool(settings.EMAIL_HOST_USER),
        "from": settings.DEFAULT_FROM_EMAIL,
    }
