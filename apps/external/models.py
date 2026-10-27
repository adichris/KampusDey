from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import private_storage
from apps.core.models import GeoPointMixin, TimeStampedModel
from apps.core.utils import random_filename
from apps.locations.models import ProvenanceMixin


class ExternalSource(TimeStampedModel):
    class Kind(models.TextChoices):
        OSM_PLACES = "osm_places", _("OpenStreetMap places")
        REMOTIVE_JOBS = "remotive_jobs", _("Remotive remote jobs")
        PARTNER_FEED = "partner_feed", _("Partner feed (RSS/Atom/JSON)")

    class Permission(models.TextChoices):
        PENDING_REVIEW = "pending_review", _("Pending review")
        APPROVED = "approved", _("Approved")
        SUSPENDED = "suspended", _("Suspended")

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=60, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    base_url = models.URLField()
    terms_url = models.URLField()
    licence = models.CharField(max_length=120, blank=True)
    attribution_text = models.CharField(max_length=200)
    permission_status = models.CharField(
        max_length=16, choices=Permission.choices, default=Permission.PENDING_REVIEW
    )
    permission_note = models.TextField(
        blank=True, help_text=_("For partner feeds: record of the publisher's written permission")
    )
    terms_reviewed = models.BooleanField(_("I have reviewed the terms at terms_url"), default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=False)
    min_interval_minutes = models.PositiveIntegerField(default=360)
    config = models.JSONField(default=dict, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_runnable(self) -> bool:
        return self.permission_status == self.Permission.APPROVED and self.enabled

    @property
    def is_live(self) -> bool:
        """Content from suspended sources is hidden immediately."""
        return self.permission_status != self.Permission.SUSPENDED


class ExternalRun(models.Model):
    class Status(models.TextChoices):
        OK = "ok", _("OK")
        PARTIAL = "partial", _("Partial")
        FAILED = "failed", _("Failed")
        SKIPPED = "skipped", _("Skipped")

    source = models.ForeignKey(ExternalSource, on_delete=models.CASCADE, related_name="runs")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OK)
    created = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    removed = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source} @ {self.started_at:%Y-%m-%d %H:%M} ({self.status})"


class PlaceKind(models.TextChoices):
    HOTEL = "hotel", _("Hotel")
    GUEST_HOUSE = "guest_house", _("Guest house")
    HOSTEL = "hostel", _("Hostel")
    MOTEL = "motel", _("Motel")
    APARTMENT = "apartment", _("Apartment")
    COPYSHOP = "copyshop", _("Printing & copy")
    HAIRDRESSER = "hairdresser", _("Salon & barber")
    BEAUTY = "beauty", _("Beauty")
    PHONE_REPAIR = "phone_repair", _("Phone shop & repair")
    COMPUTER_REPAIR = "computer_repair", _("Computer shop & repair")
    LAUNDRY = "laundry", _("Laundry")
    RESTAURANT = "restaurant", _("Restaurant / chop bar")
    FAST_FOOD = "fast_food", _("Fast food")
    CAFE = "cafe", _("Café")
    PHARMACY = "pharmacy", _("Pharmacy")
    SUPERMARKET = "supermarket", _("Supermarket / shop")
    OTHER = "other", _("Other")


ACCOMMODATION_KINDS = {"hotel", "guest_house", "hostel", "motel", "apartment"}


class PlaceQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(status__in=["unclaimed", "claim_pending", "claimed"]).exclude(
            external_source__permission_status=ExternalSource.Permission.SUSPENDED
        )


class Place(ProvenanceMixin, GeoPointMixin, TimeStampedModel):
    class Status(models.TextChoices):
        UNCLAIMED = "unclaimed", _("Unclaimed")
        CLAIM_PENDING = "claim_pending", _("Claim pending")
        CLAIMED = "claimed", _("Claimed by owner")
        HIDDEN = "hidden", _("Hidden")
        REMOVED = "removed", _("Removed")

    # ProvenanceMixin.source is a char field; the registry FK is `external_source`.
    external_source = models.ForeignKey(
        ExternalSource, on_delete=models.PROTECT, related_name="places"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    kind = models.CharField(
        max_length=16, choices=PlaceKind.choices, default=PlaceKind.OTHER, db_index=True
    )
    town = models.ForeignKey(
        "locations.Town", on_delete=models.SET_NULL, null=True, blank=True, related_name="places"
    )
    campuses = models.ManyToManyField(
        "locations.Campus", through="PlaceCampus", related_name="places"
    )
    address = models.CharField(max_length=300, blank=True)
    website = models.URLField(max_length=400, blank=True)
    opening_hours = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    description = models.TextField(
        blank=True, max_length=2000, help_text=_("Only set by a verified owner")
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    missing_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=14, choices=Status.choices, default=Status.UNCLAIMED, db_index=True
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="places",
    )
    hostel = models.ForeignKey(
        "hostels.Hostel", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reports_count = models.PositiveSmallIntegerField(default=0)

    objects = PlaceQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["external_source", "source_id"], name="uniq_place_source_id"
            )
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("external:place", args=[self.slug])

    @property
    def is_accommodation(self) -> bool:
        return self.kind in ACCOMMODATION_KINDS


class PlaceCampus(models.Model):
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="campus_links")
    campus = models.ForeignKey(
        "locations.Campus", on_delete=models.CASCADE, related_name="place_links"
    )
    distance_m = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["place", "campus"], name="uniq_place_campus")
        ]

    def __str__(self):
        return f"{self.place_id} ↔ {self.campus_id}"


def claim_proof_upload_to(instance, filename):
    return random_filename(instance, filename, "claims")


class PlaceClaim(TimeStampedModel):
    class ProofKind(models.TextChoices):
        PHOTO = "photo", _("Photo of me at the premises with the signboard")
        REGISTRATION = "registration", _("Business registration document")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="claims")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="place_claims"
    )
    proof_kind = models.CharField(max_length=14, choices=ProofKind.choices)
    proof = models.FileField(
        storage=private_storage, upload_to=claim_proof_upload_to, null=True, blank=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reason = models.CharField(max_length=300, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Claim on {self.place} by {self.user}"


class ExternalJobQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(status=ExternalJob.Status.ACTIVE).exclude(
            external_source__permission_status=ExternalSource.Permission.SUSPENDED
        )


class ExternalJob(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        EXPIRED = "expired", _("Expired")
        HIDDEN = "hidden", _("Hidden")

    external_source = models.ForeignKey(
        ExternalSource, on_delete=models.PROTECT, related_name="jobs"
    )
    source_id = models.CharField(max_length=60)
    title = models.CharField(max_length=250)
    company = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=80, blank=True)
    job_type = models.CharField(max_length=40, blank=True)
    candidate_location = models.CharField(max_length=200, blank=True)
    salary_text = models.CharField(max_length=120, blank=True)
    tags = models.JSONField(default=list, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    url = models.URLField(max_length=500)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )

    objects = ExternalJobQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["external_source", "source_id"], name="uniq_external_job"
            )
        ]

    def __str__(self):
        return self.title
