"""Chat: conversations under aliases, limits, blocks, scam warnings, share-my-number (§6.8)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.services import (
    alias_for,
    can_chat,
    can_message_first_time,
    daily_message_limit_reached,
)

from .models import Block, Conversation, Message


class ChatError(Exception):
    pass


def is_blocked(a, b) -> bool:
    if a is None or b is None:  # guest chats are blocked per conversation instead
        return False
    return Block.objects.filter(Q(blocker=a, blocked=b) | Q(blocker=b, blocked=a)).exists()


def listing_campus(listing):
    link = (
        listing.campus_links.filter(is_excluded=False)
        .select_related("campus")
        .order_by("distance_m")
        .first()
    )
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


def send_message(
    conversation: Conversation, sender, body: str, kind: str = Message.Kind.TEXT
) -> Message:
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
        raise ChatError(
            _("New accounts can send a limited number of messages per day. Try again tomorrow.")
        )
    verdict = check_message(body)
    if verdict.blocked:
        raise ChatError(verdict.message)
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        body=body[:2000],
        kind=kind,
        has_scam_warning=verdict.warn,
    )
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=["last_message_at", "updated_at"])
    if other is None:
        _email_guest(conversation, body if kind == Message.Kind.TEXT else "")
        return message
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

    card = (
        conversation.listing.contact_card
        if sender.pk == conversation.owner_id
        else default_card(sender)
    )
    channel = card.channel(kind) if card else None
    value = channel.value if channel and channel.value else ""
    if not value and kind in ("phone", "whatsapp") and sender.phone:
        value = sender.phone.as_e164
    if not value:
        raise ChatError(_("Add that contact method to your profile first."))
    label = {"phone": _("Phone"), "whatsapp": "WhatsApp", "telegram": "Telegram"}.get(kind, kind)
    return send_message(conversation, sender, f"{label}: {value}", kind=Message.Kind.SHARED_CONTACT)


def block(user, conversation: Conversation) -> Block | None:
    other = conversation.other(user)
    item = None
    if other is not None:
        item, _created = Block.objects.get_or_create(blocker=user, blocked=other)
    conversation.is_blocked = True
    conversation.save(update_fields=["is_blocked", "updated_at"])
    Message.objects.create(
        conversation=conversation,
        sender=None,
        kind=Message.Kind.SYSTEM,
        body=_("Conversation blocked."),
    )
    return item


def mark_read(conversation: Conversation, user) -> int:
    return (
        conversation.messages.exclude(sender=user)
        .filter(read_at__isnull=True)
        .update(read_at=timezone.now())
    )


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


# ---------------------------------------------------------------- guest chat (owner opt-in)


def guest_chat_allowed(listing) -> bool:
    card = listing.contact_card
    return bool(
        card
        and card.allow_guest_chat
        and card.channel("chat")
        and listing.is_visible
        and listing.effective_visibility != "members"
    )


class GuestLimitReached(ChatError):
    pass


def guest_messages_left(conversation: Conversation) -> int:
    from constance import config

    sent = conversation.messages.filter(from_guest=True).count()
    return max(config.GUEST_CHAT_MESSAGE_LIMIT - sent, 0)


def _guest_message(conversation: Conversation, body: str) -> Message:
    from apps.moderation.services import check_message
    from apps.notifications.services import notify

    if conversation.is_blocked:
        raise ChatError(_("This conversation is blocked."))
    if not conversation.is_guest:
        raise ChatError(_("This chat moved into an account. Log in to continue."))
    if conversation.pk and not guest_messages_left(conversation):
        raise GuestLimitReached(_("Sign up or log in to keep chatting. It's free."))
    body = (body or "").strip()
    if not body:
        raise ChatError(_("Write a message first."))
    verdict = check_message(body)
    if verdict.blocked:
        raise ChatError(verdict.message)
    message = Message.objects.create(
        conversation=conversation,
        sender=None,
        from_guest=True,
        body=body[:2000],
        has_scam_warning=verdict.warn,
    )
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=["last_message_at", "updated_at"])
    notify(
        conversation.owner,
        "message",
        _("New message from %(alias)s") % {"alias": conversation.starter_alias},
        body[:120],
        conversation.get_absolute_url(),
    )
    return message


@transaction.atomic
def start_guest_conversation(listing, name: str, email: str, body: str) -> Conversation:
    import secrets

    if not guest_chat_allowed(listing):
        raise ChatError(_("This seller only chats with members. Log in to send a message."))
    campus = listing_campus(listing)
    name = " ".join((name or "").split())[:40] or _("Guest")
    conversation = Conversation.objects.create(
        listing=listing,
        starter=None,
        owner=listing.owner,
        starter_alias=_("%(name)s (guest)") % {"name": name},
        owner_alias=alias_for(listing.owner, campus),
        guest_key=secrets.token_urlsafe(24),
        guest_email=(email or "").strip(),
    )
    _guest_message(conversation, body)
    if conversation.guest_email:
        _email_guest(conversation, "", first=True)
    return conversation


def guest_send(conversation: Conversation, body: str) -> Message:
    return _guest_message(conversation, body)


def _email_guest(conversation: Conversation, body: str, first: bool = False) -> None:
    """Send the guest their private chat link (never reveals the owner's details)."""
    from django.core.mail import send_mail

    from apps.core.utils import absolute_url

    if not conversation.guest_email:
        return
    link = absolute_url(conversation.get_guest_url())
    title = conversation.listing.title
    if first:
        subject = _("Your KampusDey chat about “%(title)s”") % {"title": title}
        text = _(
            "You started a chat about “%(title)s”. Open it any time with this private link:\n"
            "%(link)s\n\nKeep it to yourself: anyone with the link can read the chat. "
            "Never pay before viewing."
        ) % {"title": title, "link": link}
    else:
        subject = _("New reply about “%(title)s”") % {"title": title}
        text = _("%(alias)s replied:\n\n%(body)s\n\nOpen the chat: %(link)s") % {
            "alias": conversation.owner_alias,
            "body": body[:500],
            "link": link,
        }
    send_mail(subject, text, None, [conversation.guest_email], fail_silently=True)


@transaction.atomic
def claim_guest_conversation(conversation: Conversation, user) -> Conversation:
    """Move a guest chat into `user`'s account (after they sign up or log in)."""
    if not conversation.is_guest:
        return conversation
    if user.pk == conversation.owner_id:
        raise ChatError(_("This is your own listing."))
    campus = listing_campus(conversation.listing)
    conversation.messages.filter(from_guest=True).update(sender=user)
    existing = Conversation.objects.filter(listing=conversation.listing, starter=user).first()
    if existing:
        conversation.messages.update(conversation=existing)
        existing.last_message_at = max(
            filter(None, [existing.last_message_at, conversation.last_message_at])
        )
        existing.save(update_fields=["last_message_at", "updated_at"])
        conversation.delete()
        return existing
    conversation.starter = user
    conversation.starter_alias = alias_for(user, campus)
    conversation.guest_email = ""  # the key stays so the old link can forward to the chat
    conversation.save()
    return conversation
