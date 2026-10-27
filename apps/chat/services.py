"""Chat: conversations under aliases, limits, blocks, scam warnings, share-my-number (§6.8)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.services import alias_for, can_chat, can_message_first_time, daily_message_limit_reached

from .models import Block, Conversation, Message


class ChatError(Exception):
    pass


def is_blocked(a, b) -> bool:
    return Block.objects.filter(Q(blocker=a, blocked=b) | Q(blocker=b, blocked=a)).exists()


def listing_campus(listing):
    link = listing.campus_links.filter(is_excluded=False).select_related("campus").order_by("distance_m").first()
    return link.campus if link else None


@transaction.atomic
def start_conversation(user, listing) -> Conversation:
    if listing.owner_id == user.pk:
        raise ChatError(_("This is your own listing."))
    existing = Conversation.objects.filter(listing=listing, starter=user).first()
    if existing:
        return existing
    decision = can_message_first_time(user)
    if not decision:
        raise ChatError(decision.reason)
    if is_blocked(user, listing.owner):
        raise ChatError(_("You can't message this person."))
    campus = listing_campus(listing)
    return Conversation.objects.create(
        listing=listing,
        starter=user,
        owner=listing.owner,
        starter_alias=alias_for(user, campus),
        owner_alias=alias_for(listing.owner, campus),
    )


def send_message(conversation: Conversation, sender, body: str, kind: str = Message.Kind.TEXT) -> Message:
    from apps.moderation.services import check_message
    from apps.notifications.services import notify

    if not conversation.has_participant(sender):
        raise ChatError(_("Not your conversation."))
    decision = can_chat(sender)
    if not decision:
        raise ChatError(decision.reason)
    other = conversation.other(sender)
    if conversation.is_blocked or is_blocked(sender, other):
        raise ChatError(_("This conversation is blocked."))
    body = (body or "").strip()
    if not body:
        raise ChatError(_("Write a message first."))
    if kind == Message.Kind.TEXT and daily_message_limit_reached(sender):
        raise ChatError(_("New accounts can send a limited number of messages per day. Try again tomorrow."))
    verdict = check_message(body)
    if verdict.blocked:
        raise ChatError(verdict.message)
    message = Message.objects.create(
        conversation=conversation, sender=sender, body=body[:2000], kind=kind, has_scam_warning=verdict.warn
    )
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=["last_message_at", "updated_at"])
    notify(
        other,
        "message",
        _("New message from %(alias)s") % {"alias": conversation.alias_for(sender)},
        body[:120] if kind == Message.Kind.TEXT else "",
        conversation.get_absolute_url(),
    )
    return message


def share_contact(conversation: Conversation, sender, kind: str) -> Message:
    """Post a `shared_contact` message with the sender's chosen channel."""
    from apps.contacts.services import default_card

    card = conversation.listing.contact_card if sender.pk == conversation.owner_id else default_card(sender)
    channel = card.channel(kind) if card else None
    value = channel.value if channel and channel.value else ""
    if not value and kind in ("phone", "whatsapp") and sender.phone:
        value = sender.phone.as_e164
    if not value:
        raise ChatError(_("Add that contact method to your profile first."))
    label = {"phone": _("Phone"), "whatsapp": "WhatsApp", "telegram": "Telegram"}.get(kind, kind)
    return send_message(conversation, sender, f"{label}: {value}", kind=Message.Kind.SHARED_CONTACT)


def block(user, conversation: Conversation) -> Block:
    other = conversation.other(user)
    item, _created = Block.objects.get_or_create(blocker=user, blocked=other)
    conversation.is_blocked = True
    conversation.save(update_fields=["is_blocked", "updated_at"])
    Message.objects.create(conversation=conversation, sender=None, kind=Message.Kind.SYSTEM, body=_("Conversation blocked."))
    return item


def mark_read(conversation: Conversation, user) -> int:
    return conversation.messages.exclude(sender=user).filter(read_at__isnull=True).update(read_at=timezone.now())


def inbox(user):
    return (
        Conversation.objects.filter(Q(starter=user) | Q(owner=user))
        .select_related("listing", "starter", "owner")
        .order_by("-last_message_at", "-created_at")
    )


def unread_conversations(user) -> int:
    return (
        Message.objects.filter(Q(conversation__starter=user) | Q(conversation__owner=user))
        .exclude(sender=user)
        .filter(read_at__isnull=True)
        .values("conversation")
        .distinct()
        .count()
    )
