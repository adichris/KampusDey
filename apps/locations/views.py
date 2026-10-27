from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from . import services
from .models import Campus, CampusRequest, Region, Town


class CampusRequestForm(forms.ModelForm):
    class Meta:
        model = CampusRequest
        fields = ["name", "town_name", "region", "email"]
        labels = {"email": gettext_lazy("Your email (so we can tell you)")}


def _picker_context(request):
    query = request.GET.get("q", "").strip()
    return {
        "groups": services.campuses_by_region(query),
        "query": query,
        "regions": Region.objects.all(),
        "hint_region": services.geoip_region_hint(request),
        "next": request.GET.get("next", ""),
    }


def picker(request):
    """Bottom-sheet body (HTMX)."""
    return render(request, "locations/partials/picker.html", _picker_context(request))


def picker_page(request):
    return render(request, "locations/picker_page.html", _picker_context(request))


def campus_search(request):
    return render(request, "locations/partials/campus_list.html", _picker_context(request))


def nearest(request):
    try:
        lat, lng = float(request.GET["lat"]), float(request.GET["lng"])
    except (KeyError, ValueError):
        return HttpResponse(_("Location not available."), status=400)
    # The device position is used once for this lookup and never stored.
    campuses = services.nearest_campuses(lat, lng)
    return render(
        request,
        "locations/partials/nearest.html",
        {"campuses": campuses, "next": request.GET.get("next", "")},
    )


def towns(request):
    region = get_object_or_404(Region, pk=request.GET.get("region"))
    return render(
        request,
        "locations/partials/towns.html",
        {
            "towns": Town.objects.filter(region=region).order_by("name"),
            "region": region,
            "next": request.GET.get("next", ""),
        },
    )


def _safe_next(request, fallback="/"):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, {request.get_host()}, request.is_secure()
    ):
        return target
    return fallback


@require_POST
def choose(request):
    campus = town = None
    if request.POST.get("campus"):
        campus = get_object_or_404(Campus.objects.visible(), pk=request.POST["campus"])
    elif request.POST.get("town"):
        town = get_object_or_404(Town, pk=request.POST["town"])
    else:
        return redirect("locations:picker_page")
    fallback = campus.get_absolute_url() if campus else "/"
    response = redirect(_safe_next(request, fallback))
    if request.htmx:
        response = HttpResponse(status=204)
        response["HX-Redirect"] = _safe_next(request, fallback)
    services.set_location(request, response, campus=campus, town=town)
    return response


@ratelimit(key="ip", rate="5/h", method="POST", block=True)
def campus_request(request):
    form = CampusRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if request.user.is_authenticated:
            obj.requester = request.user
            obj.email = obj.email or request.user.email
        obj.save()
        messages.success(request, _("Thanks! We'll review your school and let you know."))
        return redirect("/")
    return render(request, "locations/campus_request.html", {"form": form})


@login_required
@require_POST
def follow(request, pk):
    from apps.accounts.services import ensure_profile

    campus = get_object_or_404(Campus.objects.visible(), pk=pk)
    profile = ensure_profile(request.user)
    if profile.followed_campuses.filter(pk=campus.pk).exists():
        profile.followed_campuses.remove(campus)
        following = False
    else:
        profile.followed_campuses.add(campus)
        following = True
    return render(
        request, "locations/partials/follow_button.html", {"campus": campus, "following": following}
    )
