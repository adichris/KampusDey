"""Signal handlers for this app."""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def claim_guest_chats(sender, request, user, **kwargs):
    """Guest chats remembered by this browser move into the account on log-in.

    Covers sign-up with email verification, where the `next` link back to the chat is lost.
    """
    if request is None:
        return
    from .models import Conversation
    from .services import ChatError, claim_guest_conversation
    from .views import _guest_keys

    keys = [k for k in _guest_keys(request).values() if isinstance(k, str) and k]
    for conv in Conversation.objects.filter(guest_key__in=keys, starter__isnull=True).exclude(
        owner=user
    ):
        try:
            claim_guest_conversation(conv, user)
        except ChatError:
            continue
