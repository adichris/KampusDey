import pytest
from django.urls import reverse

from apps.chat import services
from apps.chat.models import Conversation, Message
from tests import factories as f

pytestmark = pytest.mark.django_db


def test_two_users_can_chat(client):
    listing = f.ListingFactory()
    f.ContactChannelFactory(card=listing.contact_card, kind="chat", value="")
    buyer = f.UserFactory()
    client.force_login(buyer)
    r = client.post(reverse("chat:start", args=[listing.pk]))
    conv = Conversation.objects.get()
    assert r.url == conv.get_absolute_url()
    client.post(reverse("chat:send", args=[conv.pk]), {"body": "Hi, is it available?"}, HTTP_HX_REQUEST="true")
    client.force_login(listing.owner)
    page = client.get(conv.get_absolute_url(), HTTP_USER_AGENT="Mozilla/5.0 Mobile")
    assert b"Hi, is it available?" in page.content
    assert listing.owner.notifications.filter(trigger="message").exists()
    client.post(reverse("chat:send", args=[conv.pk]), {"body": "Yes"})
    assert conv.messages.count() == 2
    assert conv.starter_alias.startswith("KampusDey User #") or "Student #" in conv.starter_alias


def test_poll_endpoint(client):
    conv = f.ConversationFactory()
    f.MessageFactory(conversation=conv, body="ping")
    client.force_login(conv.owner)
    assert b"ping" in client.get(reverse("chat:poll", args=[conv.pk])).content


def test_outsider_cannot_read(client):
    conv = f.ConversationFactory()
    client.force_login(f.UserFactory())
    assert client.get(conv.get_absolute_url()).status_code == 404


def test_blocked_users_cannot_message():
    conv = f.ConversationFactory()
    services.block(conv.owner, conv)
    with pytest.raises(services.ChatError):
        services.send_message(conv, conv.starter, "hello?")
    with pytest.raises(services.ChatError):
        services.start_conversation(conv.starter, f.ListingFactory(owner=conv.owner))


def test_scam_keywords_show_banner(client):
    from apps.moderation.seed import seed_banned_terms

    seed_banned_terms()
    conv = f.ConversationFactory()
    msg = services.send_message(conv, conv.starter, "Please send money by MoMo first")
    assert msg.has_scam_warning
    client.force_login(conv.owner)
    assert "Never pay before viewing the room." in client.get(conv.get_absolute_url()).content.decode()
    assert not services.send_message(conv, conv.starter, "Can I view it tomorrow?").has_scam_warning


def test_share_my_number():
    user = f.UserFactory(phone="+233241112222")
    conv = f.ConversationFactory(starter=user)
    msg = services.share_contact(conv, user, "phone")
    assert msg.kind == Message.Kind.SHARED_CONTACT and "+233241112222" in msg.body


def test_unread_badge(client):
    conv = f.ConversationFactory()
    f.MessageFactory(conversation=conv)
    client.force_login(conv.owner)
    assert b"badge" in client.get(reverse("chat:unread_badge")).content
    client.get(conv.get_absolute_url())
    assert client.get(reverse("chat:unread_badge")).content == b""
