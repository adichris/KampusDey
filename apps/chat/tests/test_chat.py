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
    client.post(
        reverse("chat:send", args=[conv.pk]),
        {"body": "Hi, is it available?"},
        HTTP_HX_REQUEST="true",
    )
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
    assert (
        "Never pay before viewing the room." in client.get(conv.get_absolute_url()).content.decode()
    )
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


def _guest_listing():
    listing = f.ListingFactory()
    card = listing.contact_card
    card.allow_guest_chat = True
    card.save()
    f.ContactChannelFactory(card=card, kind="chat", value="")
    return listing


def test_guest_chat_needs_owner_opt_in(client):
    listing = f.ListingFactory()
    f.ContactChannelFactory(card=listing.contact_card, kind="chat", value="")
    assert client.get(reverse("chat:guest_start", args=[listing.pk])).status_code == 404
    from apps.contacts.channels import buttons_for

    assert "/accounts/login/" in buttons_for(listing, None)["buttons"][0]["url"]
    guest_listing = _guest_listing()
    url = buttons_for(guest_listing, None)["buttons"][0]["url"]
    assert url == reverse("chat:guest_start", args=[guest_listing.pk])


def test_guest_can_chat_and_owner_replies(client, mailoutbox):
    listing = _guest_listing()
    r = client.post(
        reverse("chat:guest_start", args=[listing.pk]),
        {"name": "Ama", "email": "ama@example.test", "body": "Is it still available?"},
    )
    conv = Conversation.objects.get()
    assert r.url == conv.get_guest_url() and conv.starter is None and conv.is_guest
    assert conv.starter_alias == "Ama (guest)"
    assert listing.owner.notifications.filter(trigger="message").exists()
    page = client.get(conv.get_guest_url())
    assert b"Is it still available?" in page.content and page["Cache-Control"].startswith("private")
    # a second visit to the start page reopens the same chat (signed cookie)
    again = client.get(reverse("chat:guest_start", args=[listing.pk]))
    assert again.url == conv.get_guest_url()
    services.send_message(conv, listing.owner, "Yes, come and see it")
    assert any("Yes, come and see it" in m.body for m in mailoutbox)
    assert "ama@example.test" not in client.get(conv.get_absolute_url()).content.decode()
    # the owner page is not readable by the guest without an account
    assert client.get(conv.get_absolute_url()).status_code == 302


def test_guest_must_sign_up_after_limit_and_chat_moves_into_account(client, settings):
    from constance.test import override_config

    listing = _guest_listing()
    with override_config(GUEST_CHAT_MESSAGE_LIMIT=2):
        client.post(
            reverse("chat:guest_start", args=[listing.pk]), {"name": "Kofi", "body": "Hello"}
        )
        conv = Conversation.objects.get()
        client.post(reverse("chat:guest_send", args=[conv.guest_key]), {"body": "Price?"})
        r = client.post(reverse("chat:guest_send", args=[conv.guest_key]), {"body": "Third"})
        assert b"Sign up to keep chatting" in r.content
        assert conv.messages.filter(from_guest=True).count() == 2
    user = f.UserFactory()
    client.force_login(user)
    claim = client.get(reverse("chat:guest_claim", args=[conv.guest_key]))
    conv.refresh_from_db()
    assert claim.url == conv.get_absolute_url()
    assert conv.starter == user and not conv.is_guest
    assert conv.messages.filter(sender=user).count() == 2
    assert client.get(conv.get_guest_url()).url == conv.get_absolute_url()
    with pytest.raises(services.ChatError):
        services.guest_send(conv, "sneaky")


def test_login_claims_guest_chats_remembered_by_the_browser(client, rf):
    from apps.chat.signals import claim_guest_chats
    from apps.chat.views import GUEST_COOKIE

    listing = _guest_listing()
    client.post(reverse("chat:guest_start", args=[listing.pk]), {"name": "Esi", "body": "Hi"})
    conv = Conversation.objects.get()
    request = rf.get("/")
    request.COOKIES[GUEST_COOKIE] = client.cookies[GUEST_COOKIE].value
    user = f.UserFactory()
    claim_guest_chats(sender=None, request=request, user=user)
    conv.refresh_from_db()
    assert conv.starter == user
