"""In-app, batched email and web-push notifications (§6.9)."""

from __future__ import annotations

import logging
from collections import defaultdict

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Notification, NotificationPreference

logger = logging.getLogger(__name__)


def prefs_for(user) -> NotificationPreference:
    prefs, _created = NotificationPreference.objects.get_or_create(
        user=user, defaults={"email_triggers": NotificationPreference.default_email_triggers()}
    )
    return prefs


def notify(user, trigger: str, title: str, body: str = "", url: str = "", extra: dict | None = None, push=True):
    if user is None or not user.is_active:
        return None
    note = Notification.objects.create(
        recipient=user,
        trigger=trigger,
        title=str(title)[:160],
        body=str(body or "")[:400],
        url=url or "",
        data={k: str(v) for k, v in (extra or {}).items()},
    )
    prefs = prefs_for(user)
    if not prefs.wants_email(trigger):
        note.email_skipped = True
        note.save(update_fields=["email_skipped"])
    if push and prefs.push_enabled:
        send_push(user, title, body, url)
    return note


def send_push(user, title, body="", url=""):
    if not settings.WEBPUSH_SETTINGS.get("VAPID_PRIVATE_KEY"):
        return False
    try:
        from webpush import send_user_notification

        send_user_notification(
            user=user,
            payload={"head": str(title), "body": str(body), "url": url or "/notifications/"},
            ttl=3600,
        )
        return True
    except Exception:
        logger.warning("web push failed for user %s", user.pk)
        return False


def send_email_batch(now=None) -> int:
    """Send one digest email per user with all their unsent notifications (≤ every 15 min)."""
    now = now or timezone.now()
    pending = (
        Notification.objects.filter(emailed_at__isnull=True, email_skipped=False)
        .select_related("recipient")
        .order_by("recipient_id", "created_at")
    )
    grouped = defaultdict(list)
    for note in pending:
        grouped[note.recipient].append(note)
    sent = 0
    for user, notes in grouped.items():
        if user.is_anonymised or not user.is_active:
            Notification.objects.filter(pk__in=[n.pk for n in notes]).update(email_skipped=True)
            continue
        context = {"user": user, "notes": notes, "SITE_URL": settings.SITE_URL}
        subject = notes[0].title if len(notes) == 1 else _("%(n)s new updates on KampusDey") % {"n": len(notes)}
        text = render_to_string("emails/notifications.txt", context)
        html = render_to_string("emails/notifications.html", context)
        msg = EmailMultiAlternatives(f"[KampusDey] {subject}", text, to=[user.email])
        msg.attach_alternative(html, "text/html")
        try:
            msg.send()
        except Exception:
            logger.exception("notification email failed")
            continue
        Notification.objects.filter(pk__in=[n.pk for n in notes]).update(emailed_at=now)
        sent += 1
    return sent


def mark_all_read(user) -> int:
    return Notification.objects.filter(recipient=user, read_at__isnull=True).update(read_at=timezone.now())
