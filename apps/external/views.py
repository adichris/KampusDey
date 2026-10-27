from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from apps.locations.models import Campus
from apps.telemetry.services import record

from . import services
from .models import Place, PlaceClaim, PlaceKind

AROUND_TABS = [
    ("stay", _l("Places to stay"), {"hotel", "guest_house", "hostel", "motel", "apartment"}),
    ("print", _l("Printing"), {"copyshop"}),
    ("hair", _l("Hair & beauty"), {"hairdresser", "beauty"}),
    ("repair", _l("Phone & computer"), {"phone_repair", "computer_repair"}),
    ("laundry", _l("Laundry"), {"laundry"}),
    ("food", _l("Food"), {"restaurant", "fast_food", "cafe"}),
    ("pharmacy", _l("Pharmacy"), {"pharmacy"}),
    ("shops", _l("Shops"), {"supermarket"}),
]


def around(request, campus_slug):
    campus = get_object_or_404(Campus.objects.visible(), slug=campus_slug)
    tab = request.GET.get("tab", "stay")
    kinds = next((k for key, _label, k in AROUND_TABS if key == tab), None)
    if kinds is None:
        raise Http404
    places = services.places_for_campus(campus, kinds)
    page = Paginator(places, 30).get_page(request.GET.get("page"))
    view_mode = request.GET.get("view", "list")
    items = [
        {"id": p.pk, "title": p.name, "url": p.get_absolute_url(), "lat": p.lat, "lng": p.lng, "approx": False,
         "info": p.get_kind_display()}
        for p in page if p.has_point
    ]
    return render(
        request,
        "external/around.html",
        {"campus": campus, "tabs": AROUND_TABS, "tab": tab, "page": page, "view_mode": view_mode, "items": items},
    )


def place(request, slug):
    obj = get_object_or_404(Place.objects.visible().select_related("external_source", "town", "hostel"), slug=slug)
    record("view", request=request, meta={"place_id": obj.pk})
    links = obj.campus_links.select_related("campus").order_by("distance_m")
    services_listings = []
    if obj.status == Place.Status.CLAIMED:
        from apps.listings.selectors import visible_listings

        services_listings = visible_listings(request.user).filter(servicedetails__place=obj)[:12]
    return render(request, "external/place.html", {"place": obj, "links": links, "services_listings": services_listings,
                                                   "is_owner": request.user.is_authenticated and obj.owner_id == request.user.pk})


def place_tap(request, slug, kind):
    obj = get_object_or_404(Place.objects.visible(), slug=slug)
    record("tap", request=request, meta={"place_id": obj.pk, "channel": kind})
    if kind == "website" and obj.website:
        return redirect(obj.website)
    if kind == "directions" and obj.has_point:
        return redirect(f"https://www.openstreetmap.org/directions?to={obj.lat}%2C{obj.lng}")
    raise Http404


class ClaimForm(forms.Form):
    proof_kind = forms.ChoiceField(choices=PlaceClaim.ProofKind.choices, widget=forms.RadioSelect)
    proof = forms.FileField(help_text=_l("Kept privately and deleted after review."))

    def clean_proof(self):
        f = self.cleaned_data["proof"]
        if f.size > 8 * 1024 * 1024:
            raise forms.ValidationError(_("Maximum 8 MB."))
        if not f.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".pdf")):
            raise forms.ValidationError(_("Upload a photo or a PDF."))
        return f


@login_required
def claim(request, slug):
    obj = get_object_or_404(Place.objects.visible(), slug=slug)
    form = ClaimForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit_claim(obj, request.user, form.cleaned_data["proof_kind"], form.cleaned_data["proof"])
        except services.ClaimError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Claim sent. We'll review it soon."))
        return redirect(obj)
    return render(request, "external/claim.html", {"place": obj, "form": form})


class PlaceEditForm(forms.ModelForm):
    class Meta:
        model = Place
        fields = ["description", "phone", "opening_hours", "website"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


@login_required
def edit_place(request, slug):
    obj = get_object_or_404(Place, slug=slug, owner=request.user, status=Place.Status.CLAIMED)
    form = PlaceEditForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
        return redirect(obj)
    return render(request, "external/edit_place.html", {"place": obj, "form": form})


__all__ = ["PlaceKind"]
