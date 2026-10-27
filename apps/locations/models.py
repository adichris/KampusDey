from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import GeoPointMixin, TimeStampedModel


class Source(models.TextChoices):
    WIKIDATA = "wikidata", "Wikidata"
    OSM = "osm", "OpenStreetMap"
    HDX = "hdx", "HDX COD-AB"
    GTEC = "gtec", "GTEC"
    MOH = "moh", _("Ministry of Health")
    WIKIPEDIA = "wikipedia", "Wikipedia"
    MANUAL = "manual", _("Manual / admin")


class ReviewStatus(models.TextChoices):
    UNVERIFIED = "unverified", _("Unverified")
    VERIFIED = "verified", _("Verified")
    REJECTED = "rejected", _("Rejected")


class ProvenanceMixin(models.Model):
    """Provenance on every location record (DATA_SOURCES_PROMPT §5)."""

    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    source_id = models.CharField(max_length=120, blank=True, db_index=True)
    source_url = models.URLField(max_length=500, blank=True)
    retrieved_at = models.DateTimeField(null=True, blank=True)
    licence = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=1.0)
    review_status = models.CharField(
        max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.UNVERIFIED, db_index=True
    )
    admin_locked = models.BooleanField(
        default=False, help_text=_("Imports never touch this record")
    )
    locked_fields = models.JSONField(default=list, blank=True)

    class Meta:
        abstract = True

    def is_field_locked(self, field: str) -> bool:
        return self.admin_locked or field in (self.locked_fields or [])


class Region(ProvenanceMixin, TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    hdx_pcode = models.CharField(max_length=20, blank=True, db_index=True)
    boundary = models.JSONField(null=True, blank=True, help_text=_("GeoJSON MultiPolygon"))
    min_lat = models.FloatField(null=True, blank=True)
    max_lat = models.FloatField(null=True, blank=True)
    min_lng = models.FloatField(null=True, blank=True)
    max_lng = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class District(ProvenanceMixin, TimeStampedModel):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="districts")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    hdx_pcode = models.CharField(max_length=20, blank=True, db_index=True)
    boundary = models.JSONField(null=True, blank=True)
    min_lat = models.FloatField(null=True, blank=True)
    max_lat = models.FloatField(null=True, blank=True)
    min_lng = models.FloatField(null=True, blank=True)
    max_lng = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["region__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.region})"


class Town(ProvenanceMixin, GeoPointMixin, TimeStampedModel):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="towns")
    district = models.ForeignKey(
        District, on_delete=models.SET_NULL, null=True, blank=True, related_name="towns"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["lat", "lng"])]

    def __str__(self):
        return f"{self.name}, {self.region.name}"

    def get_absolute_url(self):
        return reverse("listings:town_home", args=[self.slug])


class CampusKind(models.TextChoices):
    UNIVERSITY = "university", _("University")
    UNIVERSITY_COLLEGE = "university_college", _("University college")
    TECHNICAL_UNIVERSITY = "technical_university", _("Technical university")
    COLLEGE_OF_EDUCATION = "college_of_education", _("College of education")
    NURSING_MIDWIFERY = "nursing_midwifery", _("Nursing & midwifery")
    HEALTH_TRAINING = "health_training", _("Health training")
    OTHER = "other", _("Other")


class GtecStatus(models.TextChoices):
    ACCREDITED = "accredited", _("Accredited")
    EXPIRED = "expired", _("Accreditation expired")
    UNACCREDITED = "unaccredited", _("Unaccredited")
    UNKNOWN = "unknown", _("Unknown")


class Institution(ProvenanceMixin, TimeStampedModel):
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=40, blank=True)
    slug = models.SlugField(max_length=200, unique=True)
    kind = models.CharField(max_length=24, choices=CampusKind.choices, default=CampusKind.OTHER)
    website = models.URLField(blank=True)
    wikidata_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    gtec_status = models.CharField(
        max_length=14, choices=GtecStatus.choices, default=GtecStatus.UNKNOWN, db_index=True
    )
    gtec_note = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CampusQuerySet(models.QuerySet):
    def visible(self):
        """Campuses users may see: active, not rejected, not run by an unaccredited institution."""
        return (
            self.filter(is_active=True)
            .exclude(review_status=ReviewStatus.REJECTED)
            .exclude(institution__gtec_status=GtecStatus.UNACCREDITED)
            .exclude(institution__review_status=ReviewStatus.REJECTED)
        )

    def with_point(self):
        return self.filter(lat__isnull=False, lng__isnull=False)


class Campus(ProvenanceMixin, GeoPointMixin, TimeStampedModel):
    institution = models.ForeignKey(
        Institution, on_delete=models.SET_NULL, null=True, blank=True, related_name="campuses"
    )
    town = models.ForeignKey(Town, on_delete=models.PROTECT, related_name="campuses")
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=40, blank=True)
    slug = models.SlugField(max_length=200, unique=True)
    kind = models.CharField(max_length=24, choices=CampusKind.choices, default=CampusKind.OTHER)
    osm_id = models.CharField(max_length=40, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)

    objects = CampusQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = _("campuses")
        indexes = [models.Index(fields=["lat", "lng"])]

    def __str__(self):
        return self.short_name or self.name

    @property
    def label(self):
        return self.short_name or self.name

    @property
    def choice_label(self):
        """Full, searchable label for dropdowns: name, short name and town."""
        short = f" ({self.short_name})" if self.short_name and self.short_name != self.name else ""
        return f"{self.name}{short} · {self.town.name}"

    @property
    def region(self):
        return self.town.region

    def get_absolute_url(self):
        return reverse("listings:campus_home", args=[self.slug])


class AreaQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(review_status=ReviewStatus.VERIFIED)


class Area(ProvenanceMixin, GeoPointMixin, TimeStampedModel):
    town = models.ForeignKey(Town, on_delete=models.CASCADE, related_name="areas")
    campus = models.ForeignKey(
        Campus, on_delete=models.SET_NULL, null=True, blank=True, related_name="areas"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160, unique=True)
    boundary = models.JSONField(null=True, blank=True)

    objects = AreaQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.town.name})"


class CampusRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ADDED = "added", _("Added")
        REJECTED = "rejected", _("Rejected")

    name = models.CharField(_("school name"), max_length=200)
    town_name = models.CharField(_("town"), max_length=120)
    region = models.ForeignKey(Region, on_delete=models.PROTECT)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    email = models.EmailField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_campus = models.ForeignKey(Campus, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.town_name}"


class SourceRecord(TimeStampedModel):
    """Raw staging copy of every imported record so matching can re-run offline."""

    source = models.CharField(max_length=16, choices=Source.choices)
    source_id = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=40, blank=True, help_text=_("e.g. institution, campus, town")
    )
    raw = models.JSONField(default=dict)
    retrieved_at = models.DateTimeField()
    matched_content_type = models.ForeignKey(
        "contenttypes.ContentType", on_delete=models.SET_NULL, null=True, blank=True
    )
    matched_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    match_method = models.CharField(max_length=40, blank=True)
    match_score = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "kind", "source_id"], name="uniq_source_record"
            )
        ]
        indexes = [models.Index(fields=["matched_content_type", "matched_object_id"])]

    def __str__(self):
        return f"{self.source}:{self.source_id}"

    @property
    def matched(self):
        if not self.matched_content_type_id:
            return None
        model = self.matched_content_type.model_class()
        return model.objects.filter(pk=self.matched_object_id).first()


class ImportLog(TimeStampedModel):
    """Last import per source, shown on the Data sources page."""

    command = models.CharField(max_length=60)
    source = models.CharField(max_length=16, choices=Source.choices)
    summary = models.JSONField(default=dict)
    ok = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.command} @ {self.created_at:%Y-%m-%d}"


VISIBLE_CAMPUS_Q = Q(is_active=True) & ~Q(review_status=ReviewStatus.REJECTED)
