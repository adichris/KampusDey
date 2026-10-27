from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.listings.models import Listing
from apps.telemetry.services import record

from .channels import REGISTRY, PhoneHandler
from .services import send_relay_email


def _listing_for_contact(request, pk):
    listing = get_object_or_404(Listing.objects.select_related("contact_card", "owner"), pk=pk)
    if not listing.is_visible:
        raise Http404
    if listing.effective_visibility == "members" and not request.user.is_authenticated:
        raise Http404
    return listing


@require_POST
@ratelimit(key="ip", rate="60/h", method="POST", block=True)
def tap(request, pk, kind):
    """Log a contact tap, then reveal (phone) or redirect (WhatsApp, Telegram, chat)."""
    listing = _listing_for_contact(request, pk)
    handler = REGISTRY.get(kind)
    if handler is None or not handler.is_available(listing, request.user):
        raise Http404
    record("tap", request=request, listing=listing, meta={"channel": kind})
    if isinstance(handler, PhoneHandler):
        return render(request, "contacts/partials/phone_revealed.html", {"number": handler.number(listing)})
    target = handler.target(listing, request.user)
    if request.htmx:
        response = HttpResponse(status=204)
        response["HX-Redirect"] = target
        return response
    return redirect(target)


class RelayForm(forms.Form):
    body = forms.CharField(
        label=gettext_lazy("Message"), widget=forms.Textarea(attrs={"rows": 5}), max_length=2000, min_length=10
    )


@login_required
@ratelimit(key="user", rate="10/d", method="POST", block=True)
def email_relay(request, pk):
    listing = _listing_for_contact(request, pk)
    handler = REGISTRY["email"]
    if not handler.is_available(listing, request.user):
        raise Http404
    if not request.user.email_verified:
        messages.error(request, _("Verify your email address first."))
        return redirect(listing)
    form = RelayForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record("tap", request=request, listing=listing, meta={"channel": "email"})
        send_relay_email(listing, request.user, form.cleaned_data["body"])
        messages.success(request, _("Message sent. Replies come to your email."))
        return redirect(listing)
    return render(request, "contacts/email_relay.html", {"form": form, "listing": listing})
