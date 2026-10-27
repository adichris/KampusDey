import pytest
from django.urls import reverse

from apps.contacts.channels import buttons_for
from apps.engagement import services as engagement
from apps.listings.forms import ContactStepForm
from tests import factories as f

pytestmark = pytest.mark.django_db


def _listing_with(*kinds, preferred=""):
    listing = f.ListingFactory()
    card = listing.contact_card
    card.preferred_channel = preferred
    card.save()
    for order, kind in enumerate(kinds):
        value = "+233241112222" if kind in ("whatsapp", "phone") else ""
        f.ContactChannelFactory(card=card, kind=kind, value=value, order=order)
    return listing


def test_chat_is_the_default_main_button_and_seller_can_choose():
    viewer = f.UserFactory()
    listing = _listing_with("whatsapp", "chat")
    buttons = buttons_for(listing, viewer)["buttons"]
    assert [b["kind"] for b in buttons] == ["chat", "whatsapp"] and buttons[0]["primary"]
    listing = _listing_with("whatsapp", "chat", preferred="whatsapp")
    assert buttons_for(listing, viewer)["buttons"][0]["kind"] == "whatsapp"


def test_chat_button_starts_an_in_app_conversation(client):
    listing = _listing_with("whatsapp", "chat")
    buyer = f.UserFactory()
    chat = buttons_for(listing, buyer)["buttons"][0]
    assert chat["url"] == reverse("chat:start", args=[listing.pk]) and not chat["link"]
    client.force_login(buyer)
    response = client.post(chat["url"])
    assert response.status_code == 302 and "/chat/" in response.url
    assert "wa.me" not in response.url
    guest = buttons_for(listing, None)["buttons"][0]
    assert guest["link"] and guest["url"].startswith(reverse("account_login"))


def test_preferred_channel_must_be_switched_on():
    listing = f.ListingFactory()
    base = {"chat": "on", "contact_visibility": "public"}
    bad = ContactStepForm(base | {"preferred_channel": "whatsapp"}, listing=listing)
    assert not bad.is_valid() and "preferred_channel" in bad.errors
    ok = ContactStepForm(base, listing=listing)
    assert ok.is_valid() and ok.cleaned_data["preferred_channel"] == "chat"


def test_sellers_cannot_like_their_own_listing(client):
    listing = f.ListingFactory()
    with pytest.raises(engagement.EngagementError):
        engagement.toggle_like(listing.owner, listing)
    client.force_login(listing.owner)
    page = client.get(listing.get_absolute_url()).content.decode()
    assert f'id="like-{listing.pk}"' not in page
