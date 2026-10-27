from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.listings.models import Listing

from . import services
from .models import Conversation


def _conversation(request, pk) -> Conversation:
    conv = get_object_or_404(Conversation.objects.select_related("listing", "starter", "owner"), pk=pk)
    if not conv.has_participant(request.user):
        raise Http404  # admins read conversations only through a report
    return conv


@login_required
def inbox(request):
    conversations = list(services.inbox(request.user)[:100])
    for conv in conversations:
        conv.other_alias = conv.owner_alias if conv.starter_id == request.user.pk else conv.starter_alias
        conv.unread = conv.messages.exclude(sender=request.user).filter(read_at__isnull=True).exists()
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
        "other_alias": conv.owner_alias if conv.starter_id == request.user.pk else conv.starter_alias,
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
