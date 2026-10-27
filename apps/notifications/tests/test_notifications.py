import pytest
from django.core import mail
from django.urls import reverse

from apps.notifications.models import Notification
from apps.notifications.services import notify, prefs_for, send_email_batch
from tests import factories as f

pytestmark = pytest.mark.django_db


def test_email_notifications_are_batched():
    user = f.UserFactory()
    for i in range(3):
        notify(user, "message", f"Message {i}")
    assert send_email_batch() == 1
    assert len(mail.outbox) == 1 and "3 new updates" in mail.outbox[0].subject
    assert send_email_batch() == 0  # already sent


def test_email_preferences_respected():
    user = f.UserFactory()
    prefs = prefs_for(user)
    prefs.email_triggers = ["comment"]
    prefs.save()
    notify(user, "message", "No email for this")
    assert send_email_batch() == 0 and Notification.objects.get().email_skipped


def test_one_tap_links_in_email():
    user = f.UserFactory()
    notify(
        user,
        "still_available",
        "Still there?",
        extra={"confirm_url": "http://x/c", "taken_url": "http://x/t"},
    )
    send_email_batch()
    assert "http://x/c" in mail.outbox[0].body


def test_notification_list_marks_read(client_user, user):
    notify(user, "message", "Hello there")
    assert b"Hello there" in client_user.get(reverse("notifications:list")).content
    assert not Notification.objects.filter(read_at__isnull=True).exists()


def test_preferences_page(client_user, user):
    r = client_user.post(
        reverse("notifications:preferences"), {"email_triggers": ["message"], "weekly_digest": ""}
    )
    assert r.status_code == 302
    assert prefs_for(user).email_triggers == ["message"] and not prefs_for(user).weekly_digest


def test_manifest_and_offline(client, db):
    assert client.get("/manifest.webmanifest").json()["display"] == "standalone"
    assert client.get("/offline/").status_code == 200
