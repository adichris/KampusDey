import json

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.accounts.turnstile import TurnstileMixin
from apps.listings.models import Listing

from . import services
from .models import Conversation


def _conversation(request, pk) -> Conversation:
    conv = get_object_or_404(
        Conversation.objects.select_related("listing", "starter", "owner"), pk=pk
    )
    if not conv.has_participant(request.user):
        raise Http404  # admins read conversations only through a report
    return conv


@login_required
def inbox(request):
    conversations = list(services.inbox(request.user)[:100])
    for conv in conversations:
        conv.other_alias = (
            conv.owner_alias if conv.starter_id == request.user.pk else conv.starter_alias
        )
        conv.unread = (
            conv.messages.exclude(sender=request.user).filter(read_at__isnull=True).exists()
        )
    return render(request, "chat/inbox.html", {"conversations": conversations})


@login_required
def unread_badge(request):
    n = services.unread_conversations(request.user)
    if not n:
        return HttpResponse("")
    return HttpResponse(f'<span class="indicator-item badge badge-accent badge-xs">{n}</span>')


@login_required
@require_POST
def start(request, listing_pk):
    listing = get_object_or_404(Listing, pk=listing_pk)
    if not listing.is_visible:
        raise Http404
    try:
        conv = services.start_conversation(request.user, listing)
    except services.ChatError as exc:
        messages.error(request, str(exc))
        return redirect(listing)
    from apps.telemetry.services import record

    record("tap", request=request, listing=listing, meta={"channel": "chat"})
    return redirect(conv)


def _thread_context(request, conv):
    services.mark_read(conv, request.user)
    return {
        "conversation": conv,
        "chat_messages": conv.messages.select_related("sender").order_by("created_at")[:300],
        "me": request.user,
        "other_alias": conv.owner_alias
        if conv.starter_id == request.user.pk
        else conv.starter_alias,
        "my_alias": conv.alias_for(request.user),
        "blocked": conv.is_blocked or services.is_blocked(request.user, conv.other(request.user)),
    }


@login_required
def detail(request, pk):
    conv = _conversation(request, pk)
    return render(request, "chat/detail.html", _thread_context(request, conv))


@login_required
def poll(request, pk):
    conv = _conversation(request, pk)
    return render(request, "chat/partials/messages.html", _thread_context(request, conv))


@login_required
@require_POST
@ratelimit(key="user", rate="60/h", method="POST", block=True)
def send(request, pk):
    conv = _conversation(request, pk)
    try:
        services.send_message(conv, request.user, request.POST.get("body", ""))
    except services.ChatError as exc:
        ctx = _thread_context(request, conv)
        ctx["error"] = str(exc)
        return render(request, "chat/partials/messages.html", ctx)
    return render(request, "chat/partials/messages.html", _thread_context(request, conv))


@login_required
@require_POST
def share_number(request, pk):
    conv = _conversation(request, pk)
    ctx = None
    try:
        services.share_contact(conv, request.user, request.POST.get("kind", "phone"))
    except services.ChatError as exc:
        ctx = _thread_context(request, conv)
        ctx["error"] = str(exc)
    return render(request, "chat/partials/messages.html", ctx or _thread_context(request, conv))


@login_required
@require_POST
def block(request, pk):
    conv = _conversation(request, pk)
    services.block(request.user, conv)
    messages.success(request, _("Blocked. They can't message you any more."))
    return redirect("chat:inbox")


# ---------------------------------------------------------------- guest chat (owner opt-in)
GUEST_COOKIE = "kd_guest_chats"
GUEST_COOKIE_AGE = 60 * 60 * 24 * 90


class GuestStartForm(TurnstileMixin, forms.Form):
    name = forms.CharField(label=gettext_lazy("Your name"), max_length=40)
    email = forms.EmailField(
        label=gettext_lazy("Email for replies (optional)"),
        required=False,
        help_text=gettext_lazy(
            "We email you a private link to this chat. The seller never sees it."
        ),
    )
    body = forms.CharField(
        label=gettext_lazy("Message"),
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)


def _guest_keys(request) -> dict:
    try:
        data = request.get_signed_cookie(GUEST_COOKIE, default="{}", salt="guest-chat")
        keys = json.loads(data)
        return keys if isinstance(keys, dict) else {}
    except (ValueError, TypeError):
        return {}


def _guest_conversation(key) -> Conversation:
    if not key:
        raise Http404
    return get_object_or_404(Conversation.objects.select_related("listing", "owner"), guest_key=key)


@ratelimit(key="ip", rate="10/h", method="POST", block=True)
def guest_start(request, listing_pk):
    listing = get_object_or_404(Listing, pk=listing_pk)
    if request.user.is_authenticated:
        return redirect(listing)  # members use the normal chat button
    if not services.guest_chat_allowed(listing):
        raise Http404
    keys = _guest_keys(request)
    known = keys.get(str(listing.pk))
    if known and Conversation.objects.filter(guest_key=known, listing=listing).exists():
        return redirect("chat:guest_thread", key=known)
    form = GuestStartForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            conv = services.start_guest_conversation(
                listing, data["name"], data["email"], data["body"]
            )
        except services.ChatError as exc:
            form.add_error(None, str(exc))
        else:
            from apps.telemetry.services import record

            record("tap", request=request, listing=listing, meta={"channel": "chat"})
            keys[str(listing.pk)] = conv.guest_key
            response = redirect(conv.get_guest_url())
            response.set_signed_cookie(
                GUEST_COOKIE,
                json.dumps(keys),
                salt="guest-chat",
                max_age=GUEST_COOKIE_AGE,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure(),
            )
            return response
    return render(request, "chat/guest_start.html", {"listing": listing, "form": form})


def _guest_context(conv, error=""):
    left = services.guest_messages_left(conv)
    return {
        "messages_left": left,
        "limit_reached": not left,
        "claim_url": reverse("chat:guest_claim", args=[conv.guest_key]),
        "conversation": conv,
        "chat_messages": conv.messages.order_by("created_at")[:300],
        "guest_view": True,
        "other_alias": conv.owner_alias,
        "my_alias": conv.starter_alias,
        "blocked": conv.is_blocked,
        "error": error,
    }


def _private(response):
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    return response


def guest_thread(request, key):
    conv = _guest_conversation(key)
    if not conv.is_guest:  # moved into an account
        if conv.has_participant(request.user):
            return redirect(conv)
        messages.info(request, _("This chat moved into an account. Log in to continue."))
        return redirect(f"{reverse('account_login')}?next={conv.get_absolute_url()}")
    conv.messages.filter(from_guest=False, read_at__isnull=True).update(read_at=timezone.now())
    return _private(render(request, "chat/guest_detail.html", _guest_context(conv)))


def guest_poll(request, key):
    conv = _guest_conversation(key)
    if not conv.is_guest:
        return HttpResponse(status=286)  # htmx: stop polling
    return _private(render(request, "chat/partials/messages.html", _guest_context(conv)))


@require_POST
@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def guest_send(request, key):
    conv = _guest_conversation(key)
    error = ""
    try:
        services.guest_send(conv, request.POST.get("body", ""))
    except services.GuestLimitReached:
        pass  # the thread shows the sign-up prompt instead of an error
    except services.ChatError as exc:
        error = str(exc)
    return _private(render(request, "chat/partials/messages.html", _guest_context(conv, error)))


@login_required
def guest_claim(request, key):
    """After sign-up/log-in: the guest chat moves into the account, then opens normally."""
    conv = Conversation.objects.filter(guest_key=key).first() if key else None
    if conv is None:  # merged into an older chat when they logged in
        return redirect("chat:inbox")
    if not conv.is_guest:
        return redirect(conv) if conv.has_participant(request.user) else redirect("chat:inbox")
    try:
        conv = services.claim_guest_conversation(conv, request.user)
    except services.ChatError as exc:
        messages.error(request, str(exc))
        return redirect(conv.listing)
    messages.success(request, _("Your chat is now saved in your account."))
    return redirect(conv)
