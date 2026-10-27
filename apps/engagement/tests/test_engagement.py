from datetime import timedelta

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.engagement import services
from apps.engagement.models import Comment, Like, Report, SavedSearch
from tests import factories as f

pytestmark = pytest.mark.django_db


def test_masked_contacts_never_reach_database(client_user, user):
    listing = f.ListingFactory()
    client_user.post(
        reverse("engagement:comment", args=[listing.pk]),
        {"body": "call me on 024 123 4567 or kofi@example.com or www.deal.com"},
    )
    comment = Comment.objects.get()
    with connection.cursor() as cur:
        cur.execute("SELECT body FROM engagement_comment WHERE id = %s", [comment.pk])
        raw = cur.fetchone()[0]
    assert "4567" not in raw and "kofi@" not in raw and "deal.com" not in raw
    assert raw.count("[hidden]") == 3


def test_owner_reply_labelled_and_notifications():
    owner = f.UserFactory()
    asker = f.UserFactory()
    listing = f.ListingFactory(owner=owner)
    question = services.add_comment(asker, listing, "Still available?")
    reply = services.add_comment(owner, listing, "Yes", parent=question)
    assert reply.is_owner_reply and not question.is_owner_reply
    assert owner.notifications.filter(trigger="comment").exists()
    assert asker.notifications.filter(trigger="reply").exists()
    listing.refresh_from_db()
    assert listing.comments_count == 2


def test_replies_are_one_level():
    listing = f.ListingFactory()
    a = services.add_comment(f.UserFactory(), listing, "Q")
    b = services.add_comment(f.UserFactory(), listing, "R", parent=a)
    c = services.add_comment(f.UserFactory(), listing, "RR", parent=b)
    assert c.parent_id == a.pk


def test_owner_can_hide_comment():
    listing = f.ListingFactory()
    comment = services.add_comment(f.UserFactory(), listing, "rude")
    with pytest.raises(services.EngagementError):
        services.hide_comment(f.UserFactory(), comment)
    services.hide_comment(listing.owner, comment)
    assert comment.is_hidden


def test_like_toggle_and_saved_list(client_user, user):
    listing = f.ListingFactory()
    r = client_user.post(reverse("engagement:like", args=[listing.pk]))
    assert r.status_code == 200 and Like.objects.filter(user=user).exists()
    listing.refresh_from_db()
    assert listing.likes_count == 1
    assert listing.title.encode() in client_user.get(reverse("engagement:saved")).content
    client_user.post(reverse("engagement:like", args=[listing.pk]))
    listing.refresh_from_db()
    assert listing.likes_count == 0


def test_unverified_cannot_like(client):
    user = f.UserFactory(verified=False)
    client.force_login(user)
    client.post(reverse("engagement:like", args=[f.ListingFactory().pk]))
    assert not Like.objects.exists()


def test_reports_auto_hide_listing():
    listing = f.ListingFactory()
    for _ in range(3):
        services.report(f.UserFactory(), listing, "scam")
    listing.refresh_from_db()
    assert listing.is_hidden and listing.reports_count == 3
    from apps.moderation.models import ModerationItem

    assert ModerationItem.objects.filter(object_id=listing.pk, status="pending").exists()


def test_report_endpoint_for_conversation_requires_participant(client):
    conv = f.ConversationFactory()
    client.force_login(f.UserFactory())
    assert (
        client.get(reverse("engagement:report", args=["conversation", conv.pk])).status_code == 404
    )
    client.force_login(conv.starter)
    r = client.post(
        reverse("engagement:report", args=["conversation", conv.pk]), {"reason": "scam"}
    )
    assert r.status_code == 200 and Report.objects.count() == 1


def test_saved_search_alerts_only_new_matches(campus):
    user = f.UserFactory()
    saved = services.save_search(user, "buy-sell", {"price_max": "500"}, campus=campus)
    old = f.ListingFactory(price=100, published_at=timezone.now() - timedelta(days=2))
    f.ListingCampusFactory(listing=old, campus=campus)
    saved.last_notified_at = timezone.now() - timedelta(days=1)
    saved.save()
    new = f.ListingFactory(price=200)
    pricey = f.ListingFactory(price=900)
    for item in (new, pricey):
        f.ListingCampusFactory(listing=item, campus=campus)
    assert services.run_saved_search_alerts() == 1
    note = user.notifications.get(trigger="saved_search")
    assert new.title in note.body and old.title not in note.body and pricey.title not in note.body
    assert services.run_saved_search_alerts() == 0  # nothing new since last alert


def test_saved_search_endpoint(client_user, campus):
    client_user.post(
        reverse("engagement:save_search"),
        {"section": "rooms", "campus": campus.pk, "gender": "female"},
    )
    assert SavedSearch.objects.get().params == {"gender": "female"}


def test_review_requires_prior_contact():
    hostel = f.HostelFactory()
    student = f.UserFactory()
    with pytest.raises(services.EngagementError):
        services.add_review(student, 5, hostel=hostel)
    rt = f.HostelRoomTypeFactory(hostel=hostel)
    from apps.hostels.services import sync_room_type_listing

    listing = sync_room_type_listing(rt)
    f.ConversationFactory(listing=listing, starter=student)
    assert services.add_review(student, 5, "Great", hostel=hostel).rating == 5


def test_share_logs_event(client):
    from apps.telemetry.models import Event
    from apps.telemetry.services import flush

    listing = f.ListingFactory()
    client.post(reverse("engagement:share", args=[listing.pk]), {"channel": "whatsapp"})
    flush()
    assert Event.objects.get(kind="share").meta["channel"] == "whatsapp"
