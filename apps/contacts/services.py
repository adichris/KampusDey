from __future__ import annotations

from django.core.mail import EmailMessage
from django.db import transaction
from django.utils.translation import gettext as _

from apps.core.utils import absolute_url

from .models import ContactCard, ContactChannel


def default_card(owner) -> ContactCard:
    card = ContactCard.objects.filter(owner=owner, is_default=True).first()
    if card is None:
        card = ContactCard.objects.create(owner=owner, label=_("Personal"), is_default=True)
        ContactChannel.objects.create(card=card, kind=ContactChannel.Kind.CHAT, order=10)
        if owner.phone:
            ContactChannel.objects.create(
                card=card,
                kind=ContactChannel.Kind.PHONE,
                value=owner.phone.as_e164,
                is_verified=owner.phone_verified,
                order=2,
            )
    return card


@transaction.atomic
def apply_contact_step(card: ContactCard, data: dict) -> ContactCard:
    """Replace a card's channels with the ones chosen on wizard step 3."""
    wanted = {
        ContactChannel.Kind.WHATSAPP: data.get("whatsapp") or "",
        ContactChannel.Kind.PHONE: data.get("phone") or "",
        ContactChannel.Kind.TELEGRAM: data.get("telegram") or "",
        ContactChannel.Kind.EMAIL: "relay" if data.get("email_relay") else "",
        ContactChannel.Kind.CHAT: "chat" if data.get("chat") else "",
    }
    order = {"whatsapp": 1, "phone": 2, "chat": 3, "telegram": 4, "email": 5}
    owner = card.owner
    for kind, value in wanted.items():
        existing = card.channel(kind)
        if not value:
            if existing:
                existing.delete()
            continue
        stored = "" if kind in ("email", "chat") else value
        verified = bool(
            kind in ("phone", "whatsapp")
            and owner.phone_verified
            and owner.phone
            and owner.phone.as_e164 == value
        )
        if existing:
            existing.value, existing.is_verified, existing.order = stored, verified, order[kind]
            existing.save()
        else:
            ContactChannel.objects.create(
                card=card, kind=kind, value=stored, is_verified=verified, order=order[kind]
            )
    card.preferred_time = data.get("preferred_time") or ""
    card.preferred_channel = data.get("preferred_channel") or ""
    card.save()
    card._prefetched_objects_cache = {}
    return card


def initial_from_card(card: ContactCard | None) -> dict:
    if card is None:
        return {"chat": True}
    initial = {
        "preferred_time": card.preferred_time,
        "preferred_channel": card.preferred_channel or "chat",
    }
    for channel in card.channels.all():
        if channel.kind == "email":
            initial["email_relay"] = True
        elif channel.kind == "chat":
            initial["chat"] = True
        else:
            initial[channel.kind] = channel.value
    return initial


def send_relay_email(listing, sender, body: str) -> None:
    """Relay a message to the owner with the sender's verified email as Reply-To."""
    subject = _("KampusDey: message about “%(title)s”") % {"title": listing.title}
    text = _(
        "%(name)s sent you a message about your listing %(url)s:\n\n%(body)s\n\n"
        "Reply to this email to answer them directly. Never pay before viewing."
    ) % {"name": sender.public_name, "url": absolute_url(listing.get_absolute_url()), "body": body}
    EmailMessage(subject, text, to=[listing.owner.email], reply_to=[sender.email]).send()
