from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import GeoPointMixin, TimeStampedModel
from apps.listings.models import Gender, Listing, PhotoBase, RoomType


class Hostel(GeoPointMixin, TimeStampedModel):
    AMENITIES = [
        ("water", _("Reliable water")),
        ("power_backup", _("Power backup")),
        ("wifi", _("Wi-Fi")),
        ("security", _("Security / CCTV")),
        ("study_room", _("Study room")),
        ("kitchen", _("Shared kitchen")),
        ("laundry", _("Laundry area")),
        ("parking", _("Parking")),
        ("shuttle", _("Shuttle to campus")),
        ("dstv", _("TV room")),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hostels")
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True, max_length=4000)
    rules = models.TextField(blank=True, max_length=2000)
    amenities = models.JSONField(default=list, blank=True)
    town = models.ForeignKey("locations.Town", on_delete=models.PROTECT, related_name="hostels")
    campuses = models.ManyToManyField("locations.Campus", blank=True, related_name="hostels")
    contact_card = models.ForeignKey(
        "contacts.ContactCard", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("hostels:detail", args=[self.slug])

    def get_amenities_display(self):
        labels = dict(self.AMENITIES)
        return [labels.get(a, a) for a in self.amenities or []]

    @property
    def first_photo(self):
        return self.photos.first()


class HostelRoomType(TimeStampedModel):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name="room_types")
    name = models.CharField(max_length=80)
    room_type = models.CharField(max_length=16, choices=RoomType.choices, default=RoomType.SINGLE)
    gender = models.CharField(max_length=8, choices=Gender.choices, default=Gender.MIXED)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    price_period = models.CharField(
        max_length=14, choices=Listing.PricePeriod.choices, default=Listing.PricePeriod.PER_YEAR
    )
    total_rooms = models.PositiveSmallIntegerField(default=1)
    available_rooms = models.PositiveSmallIntegerField(default=1)
    listing = models.OneToOneField(
        Listing, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_room_type_link"
    )

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.hostel.name}: {self.name}"

    @property
    def occupancy_pct(self) -> int:
        if not self.total_rooms:
            return 0
        return round(100 * (self.total_rooms - self.available_rooms) / self.total_rooms)


def hostel_photo_upload_to(instance, filename):
    from apps.core.utils import random_filename

    return random_filename(instance, filename, "hostels")


class HostelPhoto(PhotoBase):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name="photos")

    def __str__(self):
        return f"Photo of {self.hostel_id}"
