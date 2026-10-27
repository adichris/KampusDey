from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.listings.models import Listing

from . import services
from .models import Comment, Report, SavedSearch

REPORTABLE = {
    "listing": ("listings", "listing"),
    "comment": ("engagement", "comment"),
    "user": ("accounts", "user"),
    "conversation": ("chat", "conversation"),
    "place": ("external", "place"),
}


def _toast(response, message, kind="success"):
    import json

    response["HX-Trigger"] = json.dumps({"showToast": {"value": str(message), "kind": kind}})
    return response


@require_POST
def like(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    if not request.user.is_authenticated:
        response = HttpResponse(status=204)
        response["HX-Redirect"] = f"/accounts/login/?next={listing.get_absolute_url()}"
        return response
    try:
        liked = services.toggle_like(request.user, listing, request)
    except services.EngagementError as exc:
        return _toast(HttpResponse(status=204), exc, "error")
    listing.refresh_from_db(fields=["likes_count"])
    response = render(
        request, "engagement/partials/like.html", {"listing": listing, "liked": liked}
    )
    return _toast(response, _("Saved") if liked else _("Removed from saved"))


@login_required
@require_POST
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def comment(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    if not listing.is_visible:
        raise Http404
    parent = None
    if request.POST.get("parent"):
        parent = get_object_or_404(Comment, pk=request.POST["parent"], listing=listing)
    try:
        obj = services.add_comment(request.user, listing, request.POST.get("body", ""), parent)
    except services.EngagementError as exc:
        return _toast(HttpResponse(status=204), exc, "error")
    if obj.is_hidden:
        return _toast(HttpResponse(""), _("Thanks — your question will show after review."))
    return render(request, "engagement/partials/comment.html", {"comment": obj, "listing": listing})


@login_required
@require_POST
def hide_comment(request, pk):
    obj = get_object_or_404(Comment.objects.select_related("listing"), pk=pk)
    try:
        services.hide_comment(request.user, obj)
    except services.EngagementError as exc:
        return _toast(HttpResponse(status=204), exc, "error")
    return _toast(HttpResponse(""), _("Comment hidden"))


@require_POST
@ratelimit(key="ip", rate="60/h", method="POST", block=True)
def share(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    services.record_share(request, listing, request.POST.get("channel", ""))
    return HttpResponse(status=204)


class ReportForm(forms.Form):
    reason = forms.ChoiceField(choices=Report.Reason.choices, widget=forms.RadioSelect)
    details = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=1000
    )

    def __init__(self, *args, kind="listing", **kwargs):
        super().__init__(*args, **kwargs)
        place_reasons = {"closed", "wrong_location", "not_real"}
        if kind == "place":
            self.fields["reason"].choices = [
                c for c in Report.Reason.choices if c[0] in place_reasons | {"other"}
            ]
        else:
            self.fields["reason"].choices = [
                c for c in Report.Reason.choices if c[0] not in place_reasons
            ]


@ratelimit(key="ip", rate="20/h", method="POST", block=True)
def report(request, kind, pk):
    if kind not in REPORTABLE:
        raise Http404
    model = ContentType.objects.get_by_natural_key(*REPORTABLE[kind]).model_class()
    target = get_object_or_404(model, pk=pk)
    if kind == "conversation" and not (
        request.user.is_authenticated and target.has_participant(request.user)
    ):
        raise Http404
    if not request.user.is_authenticated:
        return render(request, "engagement/partials/login_to_report.html")
    form = ReportForm(request.POST or None, kind=kind)
    if request.method == "POST" and form.is_valid():
        services.report(
            request.user, target, form.cleaned_data["reason"], form.cleaned_data["details"]
        )
        return render(request, "engagement/partials/report_done.html")
    return render(
        request, "engagement/partials/report_form.html", {"form": form, "kind": kind, "pk": pk}
    )


@login_required
def saved(request):
    from apps.listings.selectors import saved_listings

    return render(
        request,
        "engagement/saved.html",
        {
            "listings": saved_listings(request.user)[:100],
            "searches": SavedSearch.objects.filter(user=request.user, is_active=True),
        },
    )


@login_required
@require_POST
def save_search(request):
    from apps.locations.models import Campus, Town

    section = request.POST.get("section", "")
    campus = Campus.objects.filter(pk=request.POST.get("campus") or 0).first()
    town = Town.objects.filter(pk=request.POST.get("town") or 0).first()
    params = {
        k: v
        for k, v in request.POST.items()
        if k not in ("section", "campus", "town", "csrfmiddlewaretoken")
    }
    services.save_search(request.user, section, params, campus=campus, town=town)
    response = HttpResponse(f'<span class="badge badge-success">{_("Alert saved")}</span>')
    return _toast(response, _("We'll tell you about new matches every day."))


@login_required
@require_POST
def delete_saved_search(request, pk):
    obj = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    obj.is_active = False
    obj.save(update_fields=["is_active"])
    return HttpResponse("")


class ReviewForm(forms.Form):
    rating = forms.TypedChoiceField(
        choices=[(i, "★" * i) for i in range(5, 0, -1)], coerce=int, widget=forms.RadioSelect
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=1000
    )


@login_required
def review(request, kind, pk):
    from apps.accounts.models import User
    from apps.hostels.models import Hostel

    if kind == "hostel":
        target = get_object_or_404(Hostel, pk=pk)
        back = target.get_absolute_url()
    elif kind == "user":
        target = get_object_or_404(User, pk=pk)
        back = f"/accounts/u/{target.pk}/"
    else:
        raise Http404
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.add_review(
                request.user,
                form.cleaned_data["rating"],
                form.cleaned_data["body"],
                hostel=target if kind == "hostel" else None,
                target_user=target if kind == "user" else None,
            )
            messages.success(request, _("Thanks for your review."))
        except services.EngagementError as exc:
            messages.error(request, str(exc))
        return redirect(back)
    return render(request, "engagement/review.html", {"form": form, "target": target, "kind": kind})
