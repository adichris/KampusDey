from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from . import selectors, services
from .models import Notification, Trigger


class PreferenceForm(forms.Form):
    email_triggers = forms.MultipleChoiceField(
        label=gettext_lazy("Email me about"), choices=Trigger.choices, widget=forms.CheckboxSelectMultiple, required=False
    )
    weekly_digest = forms.BooleanField(label=gettext_lazy("Weekly 'new near you' digest"), required=False)
    push_enabled = forms.BooleanField(label=gettext_lazy("Push notifications on this device"), required=False)


@login_required
def notification_list(request):
    items = list(selectors.recent(request.user))
    response = render(request, "notifications/list.html", {"items": items})
    services.mark_all_read(request.user)
    return response


@login_required
def open_notification(request, pk):
    note = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not note.read_at:
        note.read_at = timezone.now()
        note.save(update_fields=["read_at"])
    return redirect(note.url or "notifications:list")


@login_required
def preferences(request):
    prefs = services.prefs_for(request.user)
    form = PreferenceForm(
        request.POST or None,
        initial={"email_triggers": prefs.email_triggers, "weekly_digest": prefs.weekly_digest,
                 "push_enabled": prefs.push_enabled},
    )
    if request.method == "POST" and form.is_valid():
        prefs.email_triggers = form.cleaned_data["email_triggers"]
        prefs.weekly_digest = form.cleaned_data["weekly_digest"]
        prefs.push_enabled = form.cleaned_data["push_enabled"]
        prefs.save()
        messages.success(request, _("Notification settings saved."))
        return redirect("notifications:preferences")
    return render(request, "notifications/preferences.html", {"form": form})


@login_required
@require_POST
def mark_read(request):
    services.mark_all_read(request.user)
    return redirect("notifications:list")
