"""Shared import helpers: lock-aware updates, staging records, matching (DATA_SOURCES §6)."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.core import geo
from apps.core.text import normalise_name, trigram_similarity

from ..models import Campus, ImportLog, Institution, ReviewStatus, SourceRecord, Town

LICENCES = {
    "wikidata": "CC0 1.0",
    "osm": "ODbL 1.0 — © OpenStreetMap contributors",
    "hdx": "CC BY-IGO (OCHA COD-AB; see dataset page)",
    "gtec": "Public regulator information (facts)",
    "moh": "Public document (facts)",
    "wikipedia": "Facts only (text CC BY-SA, not copied)",
}
TOWN_MAX_DISTANCE_M = 15_000
TRIGRAM_MATCH = 0.85
NEAR_M = 5_000


@dataclass
class Summary:
    command: str
    source: str
    counts: dict = field(default_factory=dict)

    def inc(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n

    def log(self, ok=True):
        ImportLog.objects.create(
            command=self.command, source=self.source, summary=self.counts, ok=ok
        )
        return self

    def lines(self):
        return [f"{k}: {v}" for k, v in sorted(self.counts.items())]


def apply_fields(obj, values: dict) -> list[str]:
    """Set fields unless locked; never overwrite with empty values. Returns changed fields."""
    if obj.pk and obj.admin_locked:
        return []
    changed = []
    for name, value in values.items():
        if value in (None, ""):
            continue
        if obj.pk and obj.is_field_locked(name):
            continue
        if getattr(obj, name) != value:
            setattr(obj, name, value)
            changed.append(name)
    return changed


def provenance(source: str, source_id: str, source_url: str = "", confidence: float = 1.0) -> dict:
    return {
        "source": source,
        "source_id": source_id,
        "source_url": source_url,
        "licence": LICENCES.get(source, ""),
        "confidence": confidence,
    }


def stage(source: str, kind: str, source_id: str, raw: dict) -> SourceRecord:
    record, created = SourceRecord.objects.get_or_create(
        source=source,
        kind=kind,
        source_id=source_id,
        defaults={"raw": raw, "retrieved_at": timezone.now()},
    )
    if not created and record.raw != raw:
        record.raw = raw
        record.retrieved_at = timezone.now()
        record.save(update_fields=["raw", "retrieved_at", "updated_at"])
    return record


def link_record(record: SourceRecord, obj, method: str, score: float):
    ct = ContentType.objects.get_for_model(obj)
    if (record.matched_content_type_id, record.matched_object_id) == (ct.pk, obj.pk):
        return  # already linked: keep the original match method and score (idempotent)
    record.matched_content_type = ct
    record.matched_object_id = obj.pk
    record.match_method = method
    record.match_score = score
    record.save(
        update_fields=[
            "matched_content_type",
            "matched_object_id",
            "match_method",
            "match_score",
            "updated_at",
        ]
    )


def save_if_changed(obj, changed: list[str], retrieved=True) -> bool:
    if not obj.pk:
        obj.retrieved_at = timezone.now()
        obj.save()
        return True
    if changed:
        if retrieved:
            obj.retrieved_at = timezone.now()
            changed = [*changed, "retrieved_at"]
        obj.save(update_fields=[*changed, "updated_at"])
        return True
    return False


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
@dataclass
class Match:
    obj: object | None
    method: str
    confidence: float


def match_institution(name: str, wikidata_id: str | None = None, region=None, point=None) -> Match:
    if wikidata_id:
        inst = Institution.objects.filter(wikidata_id=wikidata_id).first()
        if inst:
            return Match(inst, "wikidata_id", 1.0)
    norm = normalise_name(name)
    candidates = list(Institution.objects.prefetch_related("campuses__town__region"))
    for inst in candidates:
        if normalise_name(inst.name) == norm or (
            inst.short_name and normalise_name(inst.short_name) == norm
        ):
            return Match(inst, "name_exact", 0.9)
    best, best_score = None, 0.0
    for inst in candidates:
        score = trigram_similarity(norm, normalise_name(inst.name))
        if (
            score >= TRIGRAM_MATCH
            and score > best_score
            and _near_or_same_region(inst, region, point)
        ):
            best, best_score = inst, score
    if best:
        return Match(best, "trigram", 0.7)
    return Match(None, "new", 0.5)


def _near_or_same_region(inst, region, point) -> bool:
    campuses = list(inst.campuses.all())
    if not campuses:
        return region is None and point is None
    for campus in campuses:
        if region is not None and campus.town.region_id == region.pk:
            return True
        if (
            point
            and campus.has_point
            and geo.haversine_m(point[0], point[1], campus.lat, campus.lng) <= NEAR_M
        ):
            return True
    return region is None and point is None


def match_campus(name: str, point=None, region=None) -> Match:
    norm = normalise_name(name)
    for campus in Campus.objects.select_related("town__region", "institution"):
        names = {normalise_name(campus.name)}
        if campus.institution:
            names.add(normalise_name(campus.institution.name))
        if norm in names:
            return Match(campus, "name_exact", 0.9)
    best, best_score = None, 0.0
    for campus in Campus.objects.select_related("town__region"):
        score = trigram_similarity(norm, normalise_name(campus.name))
        if score < TRIGRAM_MATCH or score <= best_score:
            continue
        same_region = region is not None and campus.town.region_id == region.pk
        near = (
            point
            and campus.has_point
            and geo.haversine_m(point[0], point[1], campus.lat, campus.lng) <= NEAR_M
        )
        if same_region or near:
            best, best_score = campus, score
    if best:
        return Match(best, "trigram", 0.7)
    return Match(None, "new", 0.5)


def nearest_town(lat: float, lng: float, max_m: float = TOWN_MAX_DISTANCE_M):
    qs = geo.nearby(Town.objects.filter(lat__isnull=False), lat, lng, max_m).order_by("distance_m")
    return qs.select_related("region").first()


def find_town_by_name(name: str, region=None):
    if not name:
        return None
    norm = normalise_name(
        name.replace(" Municipal District", "").replace(" Municipal", "").replace(" District", "")
    )
    qs = Town.objects.select_related("region")
    if region is not None:
        qs = qs.filter(region=region)
    for town in qs:
        if normalise_name(town.name) == norm:
            return town
    return None


def review_status_for(confidence: float) -> str:
    return ReviewStatus.UNVERIFIED if confidence < 1.0 else ReviewStatus.UNVERIFIED
