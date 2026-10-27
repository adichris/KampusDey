"""Channel handler registry (§5.5). Adding a channel = one choice + one handler."""

from __future__ import annotations

from urllib.parse import quote

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.utils import absolute_url

from .models import ContactChannel

REGISTRY: dict[str, ChannelHandler] = {}


def register(handler_cls):
    REGISTRY[handler_cls.kind] = handler_cls()
    return handler_cls


class ChannelHandler:
    kind = ""
    label = ""
    icon = "send"
    btn_class = "btn-primary"
    # When True the button posts to the tap endpoint (logs a tap) before acting.
    reveal = False

    def channel(self, listing):
        card = listing.contact_card
        if card is None:
            return None
        return card.channel(self.kind)

    def is_available(self, listing, viewer) -> bool:
        return self.channel(listing) is not None

    def action_url(self, listing, viewer) -> str:
        return reverse("contacts:tap", args=[listing.pk, self.kind])

    def render_button(self, listing, viewer) -> dict:
        """Data for the `contact-button` component. Never includes numbers."""
        return {
            "kind": self.kind,
            "label": self.label,
            "icon": self.icon,
            "btn_class": self.btn_class,
            "url": self.action_url(listing, viewer),
            "reveal": self.reveal,
        }

    def target(self, listing, viewer) -> str:
        """Where the tap endpoint sends the user (after logging the tap)."""
        raise NotImplementedError


@register
class WhatsAppHandler(ChannelHandler):
    kind = ContactChannel.Kind.WHATSAPP
    label = "WhatsApp"
    icon = "message-circle"
    btn_class = "btn-success"

    def target(self, listing, viewer):
        digits = "".join(ch for ch in self.channel(listing).value if ch.isdigit())
        text = _("Hi, I saw your listing on KampusDey: %(title)s %(url)s") % {
            "title": listing.title,
            "url": absolute_url(listing.get_absolute_url()),
        }
        return f"https://wa.me/{digits}?text={quote(str(text))}"


@register
class PhoneHandler(ChannelHandler):
    kind = ContactChannel.Kind.PHONE
    label = _("Call")
    icon = "phone"
    btn_class = "btn-primary"
    reveal = True

    def is_available(self, listing, viewer):
        return super().is_available(listing, viewer) and not listing.hide_number

    def target(self, listing, viewer):
        return f"tel:{self.channel(listing).value}"

    def number(self, listing):
        return self.channel(listing).value


@register
class TelegramHandler(ChannelHandler):
    kind = ContactChannel.Kind.TELEGRAM
    label = "Telegram"
    icon = "send"
    btn_class = "btn-info"

    def target(self, listing, viewer):
        return f"https://t.me/{self.channel(listing).value.lstrip('@')}"


@register
class EmailRelayHandler(ChannelHandler):
    kind = ContactChannel.Kind.EMAIL
    label = _("Email")
    icon = "mail"
    btn_class = "btn-neutral"

    def action_url(self, listing, viewer):
        return reverse("contacts:email_relay", args=[listing.pk])

    def target(self, listing, viewer):
        return self.action_url(listing, viewer)


@register
class ChatHandler(ChannelHandler):
    kind = ContactChannel.Kind.CHAT
    label = _("Chat")
    icon = "message-circle"
    btn_class = "btn-secondary"

    def is_available(self, listing, viewer):
        if viewer is not None and viewer.is_authenticated and viewer.pk == listing.owner_id:
            return False
        return super().is_available(listing, viewer)

    def target(self, listing, viewer):
        return reverse("chat:start", args=[listing.pk])


def buttons_for(listing, viewer) -> dict:
    """Context for the contact bar. Members-only listings show a login prompt to guests."""
    if listing.effective_visibility == "members" and (viewer is None or not viewer.is_authenticated):
        return {"login_required": True, "buttons": []}
    order = [c.kind for c in listing.contact_card.channels.all()] if listing.contact_card else []
    buttons = []
    for kind in order:
        handler = REGISTRY.get(kind)
        if handler and handler.is_available(listing, viewer):
            buttons.append(handler.render_button(listing, viewer))
    return {"login_required": False, "buttons": buttons}
