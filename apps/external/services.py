"""Source registry gate, OSM places, Remotive jobs, partner feeds, claims (DATA_SOURCES Part 2)."""

from __future__ import annotations

import datetime as dt
import logging
import time
from datetime import timedelta

from constance import config
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core import geo
from apps.core.utils import unique_slug
from apps.locations.models import Campus, Source

from .models import (
    ACCOMMODATION_KINDS,
    ExternalJob,
    ExternalRun,
    ExternalSource,
    Place,
    PlaceCampus,
    PlaceClaim,
)

logger = logging.getLogger(__name__)

PLACES_QUERY = """[out:json][timeout:60];
(
  nwr["tourism"~"^(hotel|guest_house|hostel|motel|apartment)$"]["name"](around:{r},{lat},{lon});
  nwr["shop"~"^(copyshop|hairdresser|beauty|mobile_phone|computer|electronics|laundry|dry_cleaning|supermarket|convenience)$"]["name"](around:{r},{lat},{lon});
  nwr["amenity"~"^(restaurant|fast_food|cafe|food_court|pharmacy)$"]["name"](around:{r},{lat},{lon});
);
out center tags;"""

TAG_KIND = {
    ("tourism", "hotel"): "hotel",
    ("tourism", "guest_house"): "guest_house",
    ("tourism", "hostel"): "hostel",
    ("tourism", "motel"): "motel",
    ("tourism", "apartment"): "apartment",
    ("shop", "copyshop"): "copyshop",
    ("shop", "hairdresser"): "hairdresser",
    ("shop", "beauty"): "beauty",
    ("shop", "mobile_phone"): "phone_repair",
    ("shop", "computer"): "computer_repair",
    ("shop", "electronics"): "computer_repair",
    ("shop", "laundry"): "laundry",
    ("shop", "dry_cleaning"): "laundry",
    ("shop", "supermarket"): "supermarket",
    ("shop", "convenience"): "supermarket",
    ("amenity", "restaurant"): "restaurant",
    ("amenity", "food_court"): "restaurant",
    ("amenity", "fast_food"): "fast_food",
    ("amenity", "cafe"): "cafe",
    ("amenity", "pharmacy"): "pharmacy",
}

# Which Services category a place kind belongs under (§15.3).
SERVICE_KIND_MAP = {
    "printing": ["copyshop"],
    "hair": ["hairdresser", "beauty"],
    "phone-repair": ["phone_repair"],
    "laptop-repair": ["computer_repair"],
    "laundry": ["laundry"],
}


class SourceNotRunnable(Exception):
    pass


def kind_from_tags(tags: dict) -> str:
    for key in ("tourism", "shop", "amenity"):
        value = tags.get(key)
        if value and (key, value) in TAG_KIND:
            return TAG_KIND[(key, value)]
    return "other"


# ---------------------------------------------------------------------------
# Registry gate
# ---------------------------------------------------------------------------
def check_runnable(source: ExternalSource, now=None, force_interval=False):
    now = now or timezone.now()
    if not source.is_runnable:
        raise SourceNotRunnable(_("Source is not approved and enabled."))
    if source.last_run_at and not force_interval:
        if now - source.last_run_at < timedelta(minutes=source.min_interval_minutes):
            raise SourceNotRunnable(_("Minimum interval has not passed yet."))
    if source.kind == ExternalSource.Kind.REMOTIVE_JOBS:
        per_day = min(
            max(config.REMOTIVE_FETCHES_PER_DAY, 1), settings.REMOTIVE_HARD_MAX_FETCHES_PER_DAY
        )
        today = source.runs.filter(started_at__gte=now - timedelta(days=1)).exclude(
            status=ExternalRun.Status.SKIPPED
        )
        if today.count() >= per_day:
            raise SourceNotRunnable(_("Remotive daily fetch cap reached."))
        min_gap = timedelta(hours=24 / per_day)
        if source.last_run_at and now - source.last_run_at < min_gap:
            raise SourceNotRunnable(_("Too soon for the next Remotive fetch."))


def run_source(source: ExternalSource, fetcher=None, now=None) -> ExternalRun:
    """Run one source if allowed. `fetcher` returns recorded data in tests."""
    now = now or timezone.now()
    check_runnable(source, now)
    run = ExternalRun.objects.create(source=source, started_at=now)
    try:
        if source.kind == ExternalSource.Kind.OSM_PLACES:
            result = import_osm_places(source, fetcher=fetcher, now=now)
        elif source.kind == ExternalSource.Kind.REMOTIVE_JOBS:
            result = import_remotive_jobs(source, data=fetcher() if fetcher else None, now=now)
        else:
            result = import_partner_feed(source, data=fetcher() if fetcher else None, now=now)
        run.status = ExternalRun.Status.OK
        run.created, run.updated, run.removed = (
            result["created"],
            result["updated"],
            result["removed"],
        )
    except Exception as exc:  # recorded on the run, never raised to beat
        logger.exception("external source %s failed", source.slug)
        run.status = ExternalRun.Status.FAILED
        run.error = str(exc)[:2000]
    run.finished_at = timezone.now()
    run.save()
    source.last_run_at = now
    source.last_status = run.status
    source.save(update_fields=["last_run_at", "last_status", "updated_at"])
    return run


def run_due_sources(now=None) -> list:
    runs = []
    for source in ExternalSource.objects.filter(permission_status="approved", enabled=True):
        try:
            if source.kind == ExternalSource.Kind.OSM_PLACES and source.last_run_at:
                if (now or timezone.now()) - source.last_run_at < timedelta(
                    days=config.PLACES_REFRESH_DAYS
                ):
                    continue
            runs.append(run_source(source, now=now))
        except SourceNotRunnable:
            continue
    return runs


def approve_source(source: ExternalSource, user) -> ExternalSource:
    if not source.terms_reviewed:
        raise ValueError(_("Confirm you have reviewed the terms first."))
    if source.kind == ExternalSource.Kind.PARTNER_FEED and not source.permission_note.strip():
        raise ValueError(_("Record the publisher's written permission first."))
    source.permission_status = ExternalSource.Permission.APPROVED
    source.approved_by = user
    source.approved_at = timezone.now()
    source.save()
    return source


# ---------------------------------------------------------------------------
# OSM places
# ---------------------------------------------------------------------------
def _point(el):
    if "lat" in el:
        return el["lat"], el["lon"]
    center = el.get("center")
    return (center["lat"], center["lon"]) if center else (None, None)


def import_osm_places(source: ExternalSource, fetcher=None, now=None, sleep_s=2.0) -> dict:
    from apps.locations.importers import http

    now = now or timezone.now()
    radius = config.CAMPUS_PLACES_RADIUS_M
    seen: set[str] = set()
    stats = {"created": 0, "updated": 0, "removed": 0}
    for campus in Campus.objects.visible().with_point().select_related("town"):
        if fetcher is not None:
            data = fetcher(campus)
        else:
            data = http.overpass(PLACES_QUERY.format(r=radius, lat=campus.lat, lon=campus.lng))
            http.save_raw("osm", f"places-{campus.slug}", data)
            time.sleep(sleep_s)
        with transaction.atomic():
            for el in data.get("elements", []):
                result = _upsert_place(source, campus, el, now)
                if result:
                    stats[result] += 1
                    seen.add(f"{el['type']}/{el['id']}")
                elif result is None:
                    seen.add(f"{el['type']}/{el['id']}")
    stats["removed"] = mark_missing(source, seen, now)
    return stats


def _upsert_place(source, campus, el, now):
    tags = el.get("tags", {})
    name = tags.get("name")
    lat, lng = _point(el)
    if not name or lat is None:
        return False
    source_id = f"{el['type']}/{el['id']}"
    place = Place.objects.filter(external_source=source, source_id=source_id).first()
    created = place is None
    if created:
        place = Place(external_source=source, source_id=source_id, name=name, town=campus.town)
        place.slug = unique_slug(place, f"{name}-{campus.town.name}")
    distance = int(geo.haversine_m(campus.lat, campus.lng, lat, lng))
    if place.status == Place.Status.CLAIMED or place.admin_locked:
        PlaceCampus.objects.update_or_create(
            place=place, campus=campus, defaults={"distance_m": distance}
        )
        return None  # claimed places are never changed by refreshes
    address = ", ".join(
        p
        for p in [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:city", ""),
        ]
        if p
    )
    values = {
        "name": name,
        "kind": kind_from_tags(tags),
        "lat": lat,
        "lng": lng,
        "address": address[:300],
        "website": (tags.get("website") or tags.get("contact:website") or "")[:400],
        "opening_hours": (tags.get("opening_hours") or "")[:300],
        "phone": (tags.get("phone") or tags.get("contact:phone") or "")[:40]
        if config.IMPORT_PLACE_PHONES
        else "",
        "source": Source.OSM,
        "source_url": f"https://www.openstreetmap.org/{source_id}",
        "licence": "ODbL 1.0",
    }
    changed = False
    for key, value in values.items():
        if place.pk and place.is_field_locked(key):
            continue
        if getattr(place, key) != value:
            setattr(place, key, value)
            changed = True
    if place.missing_count or place.status == Place.Status.REMOVED:
        place.missing_count = 0
        if place.status == Place.Status.REMOVED:
            place.status = Place.Status.UNCLAIMED
        changed = True
    place.last_seen_at = now
    place.retrieved_at = now
    place.save()
    PlaceCampus.objects.update_or_create(
        place=place, campus=campus, defaults={"distance_m": distance}
    )
    if created:
        return "created"
    return "updated" if changed else None


def mark_missing(source, seen_ids: set[str], now) -> int:
    """A place missing from two consecutive refreshes becomes `removed` (claimed never)."""
    removed = 0
    for place in (
        Place.objects.filter(external_source=source)
        .exclude(source_id__in=seen_ids)
        .exclude(status__in=[Place.Status.CLAIMED, Place.Status.REMOVED])
    ):
        place.missing_count += 1
        if place.missing_count >= 2:
            place.status = Place.Status.REMOVED
            removed += 1
        place.save(update_fields=["missing_count", "status", "updated_at"])
    return removed


def places_for_campus(campus, kinds=None):
    qs = Place.objects.visible().filter(campus_links__campus=campus)
    if kinds:
        qs = qs.filter(kind__in=list(kinds))
    from django.db.models import F

    return (
        qs.annotate(distance_m=F("campus_links__distance_m"))
        .select_related("external_source")
        .order_by("distance_m", "name")
    )


def accommodation_places(campus):
    return places_for_campus(campus, ACCOMMODATION_KINDS)


def service_places(campus, service_slug=None):
    if service_slug and service_slug in SERVICE_KIND_MAP:
        return places_for_campus(campus, SERVICE_KIND_MAP[service_slug])
    kinds = {k for v in SERVICE_KIND_MAP.values() for k in v}
    return places_for_campus(campus, kinds)


# ---------------------------------------------------------------------------
# Remotive
# ---------------------------------------------------------------------------
# Remotive returns display names ("Customer Service"); admins configure slugs.
CATEGORY_ALIASES = {
    "customer-support": {"customer service", "customer support"},
    "software-dev": {"software development", "software dev"},
    "data": {"data", "data analysis"},
    "design": {"design"},
    "writing": {"writing"},
    "marketing": {"marketing"},
    "sales": {"sales", "sales / business", "business"},
}


def category_allowed(category: str, wanted: list[str]) -> bool:
    name = (category or "").strip().lower()
    slug = name.replace(" / ", "-").replace(" ", "-")
    return any(item in (name, slug) or name in CATEGORY_ALIASES.get(item, set()) for item in wanted)


def _keywords(value: str) -> list[str]:
    return [p.strip().lower() for p in (value or "").split(",") if p.strip()]


@transaction.atomic
def import_remotive_jobs(source: ExternalSource, data: dict | None = None, now=None) -> dict:
    from apps.locations.importers import http

    now = now or timezone.now()
    if data is None:
        resp = http.fetch(source.base_url, params={"limit": 300}, min_interval=31)
        data = resp.json()
        http.save_raw("remotive", "jobs", data)
    locations = _keywords(config.REMOTIVE_LOCATION_KEYWORDS)
    categories = _keywords(config.REMOTIVE_CATEGORIES)
    stats = {"created": 0, "updated": 0, "removed": 0}
    seen = set()
    for job in data.get("jobs", []):
        loc = (job.get("candidate_required_location") or "").lower()
        if locations and not any(k in loc for k in locations):
            continue
        if categories and not category_allowed(job.get("category"), categories):
            continue
        source_id = str(job.get("id"))
        seen.add(source_id)
        published = parse_datetime(job.get("publication_date") or "")
        if published and timezone.is_naive(published):
            published = timezone.make_aware(published, dt.UTC)
        values = {
            "title": (job.get("title") or "")[:250],
            "company": (job.get("company_name") or "")[:200],
            "category": job.get("category") or "",
            "job_type": (job.get("job_type") or "").replace("_", " "),
            "candidate_location": (job.get("candidate_required_location") or "")[:200],
            "salary_text": (job.get("salary") or "")[:120],
            "tags": list(job.get("tags") or [])[:10],
            "published_at": published,
            "url": job.get("url") or "",
            "last_seen_at": now,
        }
        # The full description is deliberately never stored (§16.2).
        obj = ExternalJob.objects.filter(external_source=source, source_id=source_id).first()
        if obj is None:
            ExternalJob.objects.create(
                external_source=source, source_id=source_id, first_seen_at=now, **values
            )
            stats["created"] += 1
        else:
            if obj.status == ExternalJob.Status.EXPIRED:
                obj.status = ExternalJob.Status.ACTIVE
            for k, v in values.items():
                setattr(obj, k, v)
            obj.save()
            stats["updated"] += 1
    cutoff = now - timedelta(days=config.EXTERNAL_JOB_MAX_AGE_DAYS)
    stale = ExternalJob.objects.filter(
        external_source=source, status=ExternalJob.Status.ACTIVE
    ).exclude(source_id__in=seen)
    stats["removed"] += stale.update(status=ExternalJob.Status.EXPIRED)
    stats["removed"] += ExternalJob.objects.filter(
        external_source=source, status=ExternalJob.Status.ACTIVE, published_at__lt=cutoff
    ).update(status=ExternalJob.Status.EXPIRED)
    return stats


# ---------------------------------------------------------------------------
# Partner feeds (RSS/Atom/JSON) — only with written permission
# ---------------------------------------------------------------------------
def import_partner_feed(source: ExternalSource, data=None, now=None) -> dict:
    """JSON Feed / simple JSON list adapter. Items become ExternalJobs labelled with the source."""
    from apps.locations.importers import http

    now = now or timezone.now()
    if data is None:
        data = http.fetch(source.base_url, min_interval=60).json()
    items = data.get("items") or data.get("jobs") or (data if isinstance(data, list) else [])
    stats = {"created": 0, "updated": 0, "removed": 0}
    seen = set()
    for item in items:
        source_id = str(item.get("id") or item.get("url"))
        url = item.get("url") or item.get("link")
        if not source_id or not url:
            continue
        seen.add(source_id)
        _obj, created = ExternalJob.objects.update_or_create(
            external_source=source,
            source_id=source_id,
            defaults={
                "title": (item.get("title") or "")[:250],
                "company": str(item.get("company") or (item.get("author") or {}).get("name", ""))[
                    :200
                ],
                "url": url,
                "published_at": parse_datetime(
                    item.get("date_published") or item.get("published") or ""
                )
                or now,
                "last_seen_at": now,
                "status": ExternalJob.Status.ACTIVE,
            },
        )
        stats["created" if created else "updated"] += 1
    stats["removed"] = (
        ExternalJob.objects.filter(external_source=source, status="active")
        .exclude(source_id__in=seen)
        .update(status=ExternalJob.Status.EXPIRED)
    )
    return stats


# ---------------------------------------------------------------------------
# Claim flow (§15.4)
# ---------------------------------------------------------------------------
class ClaimError(Exception):
    pass


def submit_claim(place: Place, user, proof_kind: str, proof_file) -> PlaceClaim:
    if not user.is_authenticated or not user.email_verified:
        raise ClaimError(_("Verify your email address before claiming a place."))
    if place.status not in (Place.Status.UNCLAIMED,):
        raise ClaimError(_("This place can't be claimed right now."))
    if not proof_file:
        raise ClaimError(_("Add a proof photo or document."))
    claim = PlaceClaim.objects.create(place=place, user=user, proof_kind=proof_kind)
    claim.proof.save(proof_file.name, proof_file, save=True)
    place.status = Place.Status.CLAIM_PENDING
    place.save(update_fields=["status", "updated_at"])
    return claim


@transaction.atomic
def decide_claim(claim: PlaceClaim, approve: bool, reviewer, reason: str = "") -> PlaceClaim:
    from apps.accounts.services import ensure_profile
    from apps.hostels.models import Hostel
    from apps.notifications.services import notify

    place = claim.place
    claim.status = PlaceClaim.Status.APPROVED if approve else PlaceClaim.Status.REJECTED
    claim.reason = reason
    claim.reviewed_by = reviewer
    claim.reviewed_at = timezone.now()
    if claim.proof:
        claim.proof.delete(save=False)  # proof is deleted after review
    claim.proof = None
    claim.save()
    if approve:
        place.owner = claim.user
        place.status = Place.Status.CLAIMED
        place.admin_locked = True
        if place.is_accommodation and place.hostel_id is None:
            profile = ensure_profile(claim.user)
            if profile.role not in ("landlord", "agent"):
                profile.role = "landlord"
                profile.save(update_fields=["role"])
            hostel = Hostel(
                owner=claim.user,
                name=place.name,
                town=place.town or place.campuses.first().town,
                lat=place.lat,
                lng=place.lng,
            )
            hostel.slug = unique_slug(hostel, place.name)
            hostel.save()
            hostel.campuses.set(place.campuses.all())
            place.hostel = hostel
        place.save()
        notify(
            claim.user,
            "claim",
            _("Your claim for %(name)s was approved") % {"name": place.name},
            url=place.hostel.get_absolute_url() if place.hostel_id else place.get_absolute_url(),
        )
    else:
        place.status = Place.Status.UNCLAIMED
        place.save(update_fields=["status", "updated_at"])
        notify(
            claim.user,
            "claim",
            _("Your claim for %(name)s was not approved") % {"name": place.name},
            reason,
        )
    return claim
