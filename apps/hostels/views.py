from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Avg
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.contacts.channels import buttons_for
from apps.contacts.services import default_card
from apps.core.images import clean_image
from apps.locations.models import Campus

from . import services
from .models import Hostel, HostelPhoto, HostelRoomType


class HostelForm(forms.ModelForm):
    amenities = forms.MultipleChoiceField(
        choices=Hostel.AMENITIES, widget=forms.CheckboxSelectMultiple, required=False
    )
    lat = forms.FloatField(required=False, widget=forms.HiddenInput)
    lng = forms.FloatField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Hostel
        fields = ["name", "description", "rules", "amenities", "town", "campuses"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "rules": forms.Textarea(attrs={"rows": 3}),
            "campuses": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campuses"].queryset = Campus.objects.visible().select_related("town")
        self.fields["campuses"].required = False
        if self.instance.pk and self.instance.has_point and not self.is_bound:
            self.initial.update(lat=self.instance.lat, lng=self.instance.lng)


class RoomTypeForm(forms.ModelForm):
    class Meta:
        model = HostelRoomType
        fields = [
            "name",
            "room_type",
            "gender",
            "price",
            "price_period",
            "total_rooms",
            "available_rooms",
        ]

    def clean(self):
        data = super().clean()
        if data.get("available_rooms") is not None and data.get("total_rooms") is not None:
            if data["available_rooms"] > data["total_rooms"]:
                self.add_error("available_rooms", _("Can't be more than the total."))
        if data.get("price") is not None and data["price"] < 0:
            self.add_error("price", _("Price cannot be negative."))
        return data


def _require_manager(user):
    if not services.can_manage_hostels(user):
        raise PermissionDenied(_("Set your role to landlord or agent to manage hostels."))


def _own(request, pk):
    return get_object_or_404(Hostel, pk=pk, owner=request.user)


@login_required
def manager(request):
    if not services.can_manage_hostels(request.user):
        return render(request, "hostels/not_manager.html")
    hostels = Hostel.objects.filter(owner=request.user).prefetch_related("room_types")
    rows = [{"hostel": h, "occupancy": services.occupancy(h)} for h in hostels]
    return render(request, "hostels/manager.html", {"rows": rows})


@login_required
def edit_hostel(request, pk=None):
    _require_manager(request.user)
    hostel = _own(request, pk) if pk else None
    form = HostelForm(
        request.POST or None,
        instance=hostel,
        initial={"town": request.location.effective_town} if not hostel else None,
    )
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        from apps.listings.services import ListingError, set_point

        try:
            set_point(obj, form.cleaned_data.get("lat"), form.cleaned_data.get("lng"))
        except ListingError as exc:
            form.add_error(None, str(exc))
            return render(request, "hostels/edit.html", {"form": form, "hostel": hostel})
        if not obj.pk:
            obj.owner = request.user
            obj.contact_card = default_card(request.user)
            from apps.core.utils import unique_slug

            obj.slug = unique_slug(obj, obj.name)
        obj.save()
        form.save_m2m()
        for rt in obj.room_types.all():
            services.sync_room_type_listing(rt)
        messages.success(request, _("Hostel saved."))
        return redirect("hostels:manage", pk=obj.pk)
    return render(request, "hostels/edit.html", {"form": form, "hostel": hostel})


@login_required
def manage(request, pk):
    hostel = _own(request, pk)
    return render(
        request,
        "hostels/manage.html",
        {
            "hostel": hostel,
            "room_types": hostel.room_types.select_related("listing"),
            "occupancy": services.occupancy(hostel),
            "stats": services.room_type_stats(hostel),
            "photos": hostel.photos.all(),
            "form": RoomTypeForm(),
        },
    )


@login_required
def room_type(request, pk, rt_pk=None):
    hostel = _own(request, pk)
    instance = get_object_or_404(HostelRoomType, pk=rt_pk, hostel=hostel) if rt_pk else None
    form = RoomTypeForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.hostel = hostel
        obj.save()
        services.sync_room_type_listing(obj)
        messages.success(request, _("Room type saved."))
        return redirect("hostels:manage", pk=hostel.pk)
    return render(
        request, "hostels/room_type.html", {"form": form, "hostel": hostel, "instance": instance}
    )


@login_required
@require_POST
def step(request, pk, rt_pk, delta):
    hostel = _own(request, pk)
    rt = get_object_or_404(HostelRoomType, pk=rt_pk, hostel=hostel)
    services.step_available(rt, 1 if delta == "up" else -1)
    rt.refresh_from_db()
    return render(request, "hostels/partials/stepper.html", {"rt": rt, "hostel": hostel})


@login_required
@require_POST
def photo_upload(request, pk):
    hostel = _own(request, pk)
    upload = request.FILES.get("photo")
    if not upload:
        return HttpResponse(_("No photo received."), status=400)
    try:
        content, width, height, phash = clean_image(upload, 8)
    except ValidationError as exc:
        return HttpResponse(" ".join(exc.messages), status=400)
    photo = HostelPhoto(hostel=hostel, phash=phash, order=hostel.photos.count() + 1)
    photo.image.save(content.name, content, save=False)
    photo.save()
    return render(
        request, "hostels/partials/photos.html", {"hostel": hostel, "photos": hostel.photos.all()}
    )


@login_required
@require_POST
def photo_delete(request, pk, photo_pk):
    hostel = _own(request, pk)
    photo = get_object_or_404(HostelPhoto, pk=photo_pk, hostel=hostel)
    photo.image.delete(save=False)
    photo.delete()
    return render(
        request, "hostels/partials/photos.html", {"hostel": hostel, "photos": hostel.photos.all()}
    )


@login_required
def inquiries(request, pk):
    hostel = _own(request, pk)
    conversations, taps = services.inquiries(hostel)
    return render(
        request,
        "hostels/inquiries.html",
        {"hostel": hostel, "conversations": conversations, "taps": taps},
    )


def detail(request, slug):
    from apps.engagement.services import can_review_hostel

    hostel = get_object_or_404(
        Hostel.objects.select_related("town__region", "owner__profile"), slug=slug
    )
    room_types = hostel.room_types.select_related("listing")
    listing = next((rt.listing for rt in room_types if rt.listing and rt.listing.is_visible), None)
    reviews = hostel.reviews.filter(status="visible").select_related("reviewer")
    return render(
        request,
        "hostels/detail.html",
        {
            "hostel": hostel,
            "room_types": room_types,
            "photos": hostel.photos.all(),
            "reviews": reviews[:30],
            "rating": reviews.aggregate(avg=Avg("rating"))["avg"],
            "contact": buttons_for(listing, request.user)
            if listing
            else {"buttons": [], "login_required": False},
            "can_review": can_review_hostel(request.user, hostel),
        },
    )
