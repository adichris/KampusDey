"""Telemetry write path (buffer + flush), dedupe, roll-ups and retention (§6.12)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, timedelta

from constance import config
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.utils import is_bot, session_hash

from .models import DailyCampusStats, DailyListingStats, Event, PendingEvent

logger = logging.getLogger(__name__)
REDIS_LIST_KEY = "kd:telemetry:buffer"
DEDUPE_TTL = 60 * 60 * 24


def _redis():
    if not settings.REDIS_URL:
        return None
    try:
        import redis

        return redis.Redis.from_url(settings.REDIS_URL)
    except Exception:  # pragma: no cover - redis misconfigured
        return None


def _session_key(request) -> str:
    if request is None or not hasattr(request, "session"):
        return ""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def build_payload(kind, request=None, user=None, listing=None, meta=None, campus=None, town=None):
    location = getattr(request, "location", None) if request is not None else None
    if campus is None and location is not None:
        campus = location.campus
        town = town or location.effective_town
    if user is None and request is not None and request.user.is_authenticated:
        user = request.user
    meta = dict(meta or {})
    if campus is None and town is None and request is not None and kind in ("search", "view"):
        from apps.locations.services import geoip_region_hint

        region = geoip_region_hint(request)
        if region:
            meta["region"] = region.name  # GeoLite2 region only as fallback, no IP stored
    return {
        "kind": kind,
        "listing_id": getattr(listing, "pk", None),
        "user_id": getattr(user, "pk", None),
        "session_hash": session_hash(_session_key(request)) if request is not None else "",
        "campus_id": getattr(campus, "pk", None),
        "town_id": getattr(town, "pk", None) or (getattr(listing, "town_id", None) if listing else None),
        "section": getattr(listing, "section", "") or meta.pop("section", ""),
        "meta": meta,
        "created_at": timezone.now().isoformat(),
    }


def record(kind, request=None, user=None, listing=None, meta=None, campus=None, town=None) -> bool:
    """Queue an event. Never blocks the request on the events table; returns False if skipped."""
    try:
        if request is not None and is_bot(request.META.get("HTTP_USER_AGENT")) and kind in ("view", "search"):
            return False
        payload = build_payload(kind, request, user, listing, meta, campus, town)
        if kind == "view" and listing is not None:
            key = f"kd:view:{payload['session_hash']}:{listing.pk}:{timezone.localdate().isoformat()}"
            if not cache.add(key, 1, DEDUPE_TTL):
                return False
        push(payload)
        return True
    except Exception:  # telemetry must never break a page
        logger.exception("telemetry record failed")
        return False


def push(payload: dict) -> None:
    client = _redis()
    if client is not None:
        try:
            client.rpush(REDIS_LIST_KEY, json.dumps(payload))
            return
        except Exception:
            logger.warning("Redis unavailable; using database buffer")
    PendingEvent.objects.create(payload=payload)


def _to_event(payload: dict) -> Event:
    created = parse_datetime(payload.get("created_at") or "") or timezone.now()
    return Event(
        kind=payload["kind"],
        listing_id=payload.get("listing_id"),
        user_id=payload.get("user_id"),
        session_hash=payload.get("session_hash", ""),
        campus_id=payload.get("campus_id"),
        town_id=payload.get("town_id"),
        section=payload.get("section", ""),
        meta=payload.get("meta") or {},
        created_at=created,
    )


def flush(max_items: int = 5000) -> int:
    """Move buffered events into the Event table in bulk. Safe to run concurrently."""
    created = 0
    client = _redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.lrange(REDIS_LIST_KEY, 0, max_items - 1)
            pipe.ltrim(REDIS_LIST_KEY, max_items, -1)
            raw, _ok = pipe.execute()
            events = [_to_event(json.loads(r)) for r in raw]
            Event.objects.bulk_create(events, batch_size=500)
            created += len(events)
        except Exception:
            logger.exception("flush from redis failed")
    with transaction.atomic():
        pending = list(PendingEvent.objects.select_for_update(skip_locked=True).order_by("pk")[:max_items])
        if pending:
            Event.objects.bulk_create([_to_event(p.payload) for p in pending], batch_size=500)
            PendingEvent.objects.filter(pk__in=[p.pk for p in pending]).delete()
            created += len(pending)
    return created


def rollup(day: date | None = None) -> dict:
    """Nightly roll-up into daily stats; idempotent (recomputes the whole day)."""
    from apps.listings.models import Listing

    flush()
    day = day or (timezone.localdate() - timedelta(days=1))
    start = timezone.make_aware(timezone.datetime(day.year, day.month, day.day))
    end = start + timedelta(days=1)
    events = Event.objects.filter(created_at__gte=start, created_at__lt=end)

    per_listing: dict[int, dict] = defaultdict(lambda: {"views": 0, "taps": 0, "likes": 0, "shares": 0, "taps_by_channel": {}})
    for row in events.filter(listing__isnull=False).values("listing_id", "kind", "meta"):
        stats = per_listing[row["listing_id"]]
        if row["kind"] == "view":
            stats["views"] += 1
        elif row["kind"] == "tap":
            stats["taps"] += 1
            channel = (row["meta"] or {}).get("channel", "other")
            stats["taps_by_channel"][channel] = stats["taps_by_channel"].get(channel, 0) + 1
        elif row["kind"] == "like":
            stats["likes"] += 1
        elif row["kind"] == "share":
            stats["shares"] += 1
    from apps.engagement.models import Comment

    comment_counts = dict(
        Comment.objects.filter(created_at__gte=start, created_at__lt=end)
        .values_list("listing_id")
        .annotate(n=Count("id"))
    )
    existing_ids = set(Listing.objects.filter(pk__in=set(per_listing) | set(comment_counts)).values_list("pk", flat=True))
    for listing_id in existing_ids:
        stats = per_listing.get(listing_id, {"views": 0, "taps": 0, "likes": 0, "shares": 0, "taps_by_channel": {}})
        DailyListingStats.objects.update_or_create(
            listing_id=listing_id, date=day, defaults={**stats, "comments": comment_counts.get(listing_id, 0)}
        )

    per_campus: dict[int, dict] = defaultdict(lambda: defaultdict(int))
    for row in events.filter(campus__isnull=False).values("campus_id", "kind", "meta"):
        stats = per_campus[row["campus_id"]]
        kind = row["kind"]
        if kind == "view":
            stats["views"] += 1
        elif kind == "tap":
            stats["taps"] += 1
        elif kind == "search":
            stats["searches"] += 1
            if not (row["meta"] or {}).get("results"):
                stats["zero_result_searches"] += 1
        elif kind == "signup":
            stats["signups"] += 1
        elif kind == "post":
            stats["posts"] += 1
    for campus_id, stats in per_campus.items():
        DailyCampusStats.objects.update_or_create(campus_id=campus_id, date=day, defaults=dict(stats))

    update_rolling_counters()
    deleted = cleanup_raw()
    return {"listings": len(existing_ids), "campuses": len(per_campus), "deleted_raw": deleted}


def update_rolling_counters() -> int:
    """Refresh views_7d / taps_7d / likes_7d on listings from raw events."""
    from apps.listings.models import Listing

    since = timezone.now() - timedelta(days=7)
    counts = defaultdict(lambda: {"view": 0, "tap": 0, "like": 0})
    for row in (
        Event.objects.filter(created_at__gte=since, listing__isnull=False, kind__in=["view", "tap", "like"])
        .values("listing_id", "kind")
        .annotate(n=Count("id"))
    ):
        counts[row["listing_id"]][row["kind"]] = row["n"]
    Listing.objects.exclude(pk__in=list(counts)).filter(views_7d__gt=0).update(views_7d=0, taps_7d=0, likes_7d=0)
    batch = []
    for listing in Listing.objects.filter(pk__in=list(counts)):
        c = counts[listing.pk]
        listing.views_7d, listing.taps_7d, listing.likes_7d = c["view"], c["tap"], c["like"]
        batch.append(listing)
    Listing.objects.bulk_update(batch, ["views_7d", "taps_7d", "likes_7d"], batch_size=500)
    return len(batch)


def cleanup_raw() -> int:
    cutoff = timezone.now() - timedelta(days=config.TELEMETRY_RAW_RETENTION_DAYS)
    deleted, _ = Event.objects.filter(created_at__lt=cutoff).delete()
    return deleted
