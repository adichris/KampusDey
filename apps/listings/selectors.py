"""Read-side queries: feeds, section pages, search, boosted slots, related listings."""

from __future__ import annotations

import random
from datetime import timedelta

from constance import config
from django.db import connection
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.utils import timezone

from apps.boosts.models import Boost
from apps.core import geo

from .models import Listing, ListingPhoto
from .sections import SECTIONS

CARD_PREFETCH = Prefetch("photos", queryset=ListingPhoto.objects.order_by("order", "id"))


def base_queryset():
    return Listing.objects.select_related("town", "area", "owner__profile").prefetch_related(
        CARD_PREFETCH
    )


def visible_listings(viewer=None, sections=None):
    """Listings anyone (or this viewer) may see in feeds and search."""
    qs = base_queryset().filter(status__in=Listing.VISIBLE_STATUSES, is_hidden=False)
    if sections is not None:
        qs = qs.filter(section__in=list(sections))
    if viewer is None or not viewer.is_authenticated:
        # `need_food` posts never appear in public feeds for guests (§6.3).
        qs = qs.exclude(section="food", fooddetails__post_kind="need_food")
    return qs


def for_location(qs, location):
    if location is None or not location.is_set:
        return qs
    if location.campus:
        linked = Q(campus_links__campus=location.campus, campus_links__is_excluded=False)
        return qs.filter(linked).distinct()
    return qs.filter(town=location.effective_town)


def for_campus(qs, campus):
    return qs.filter(campus_links__campus=campus, campus_links__is_excluded=False).distinct()


def for_town(qs, town):
    return qs.filter(town=town)


def with_distance(qs, point):
    if not point:
        return qs
    lat, lng = point
    return geo.annotate_distance(qs.filter(lat__isnull=False), lat, lng)


def sort_listings(qs, sort: str, point=None):
    if sort == "newest":
        return qs.order_by("-published_at")
    if sort == "price":
        return qs.order_by("price", "-published_at")
    if sort == "price_desc":
        return qs.order_by("-price", "-published_at")
    if sort == "distance" and point:
        from django.db.models import F

        return annotate_point_distance(qs, point).order_by(
            F("distance_m").asc(nulls_last=True), "-score"
        )
    return qs.order_by("-score", "-published_at")


def annotate_point_distance(qs, point):
    """Distance in metres (NULL for listings without a point)."""
    return geo.annotate_distance(qs, point[0], point[1])


def active_boost_ids(now=None) -> set[int]:
    now = now or timezone.now()
    return set(Boost.objects.active(now).values_list("listing_id", flat=True))


def boosted_slots(qs, limit=None, now=None, exclude_ids=()):
    """Up to BOOST_SLOTS_PER_PAGE boosted listings, rotated per 10-minute window."""
    limit = config.BOOST_SLOTS_PER_PAGE if limit is None else limit
    now = now or timezone.now()
    boosted = qs.filter(Exists(Boost.objects.active(now).filter(listing=OuterRef("pk")))).exclude(
        pk__in=list(exclude_ids)
    )
    items = list(boosted.order_by("pk")[:200])
    window = int(now.timestamp() // 600)
    random.Random(window).shuffle(items)
    return items[: max(limit, 0)]


def home_feeds(location, viewer, enabled_slugs, point=None):
    qs = for_location(visible_listings(viewer, enabled_slugs), location)
    boosted = boosted_slots(qs)
    boosted_ids = {b.pk for b in boosted}
    since = timezone.now() - timedelta(days=1)
    new_today = list(
        qs.filter(published_at__gte=since)
        .exclude(pk__in=boosted_ids)
        .order_by("-published_at")[:12]
    )
    near_point = point or (location.point if location else None)
    if near_point:
        near = list(
            with_distance(qs.exclude(pk__in=boosted_ids), near_point).order_by(
                "distance_m", "-score"
            )[:12]
        )
    else:
        near = list(qs.exclude(pk__in=boosted_ids).order_by("-score")[:12])
    return {"boosted": boosted, "near": near, "new_today": new_today}


def related_listings(listing, viewer=None, limit=6):
    qs = visible_listings(viewer, [listing.section]).exclude(pk=listing.pk)
    campus_ids = list(
        listing.campus_links.filter(is_excluded=False).values_list("campus_id", flat=True)
    )
    if campus_ids:
        qs = qs.filter(campus_links__campus_id__in=campus_ids).distinct()
    else:
        qs = qs.filter(town=listing.town)
    return list(qs.order_by("-score")[:limit])


def search(query: str, location, viewer, enabled_slugs, section: str | None = None):
    """Full-text search (PostgreSQL) or icontains fallback (SQLite). Returns (qs, facets)."""
    qs = for_location(visible_listings(viewer, enabled_slugs), location)
    query = (query or "").strip()
    if query:
        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import SearchQuery, SearchRank
            from django.db.models import F

            sq = SearchQuery(query, search_type="websearch", config="english")
            qs = qs.filter(search_vector=sq).annotate(rank=SearchRank(F("search_vector"), sq))
            qs = qs.order_by("-rank", "-score")
        else:
            terms = [t for t in query.split() if t]
            for term in terms:
                qs = qs.filter(Q(title__icontains=term) | Q(description__icontains=term))
            qs = qs.order_by("-score")
    facets_qs = qs.order_by().values("section").annotate(n=Count("id", distinct=True))
    facets = [
        {"section": SECTIONS[row["section"]], "count": row["n"]}
        for row in facets_qs
        if row["section"] in SECTIONS
    ]
    facets.sort(key=lambda f: -f["count"])
    if section:
        qs = qs.filter(section=section)
    return qs, facets


def for_map(qs, limit=300):
    """Listings with a point, for map views. Sensitive sections are rendered as circles."""
    rows = []
    for item in qs.filter(lat__isnull=False)[:limit]:
        rows.append(
            {
                "id": item.pk,
                "title": item.title,
                "url": item.get_absolute_url(),
                "lat": item.lat,
                "lng": item.lng,
                "section": item.section,
                "approx": item.is_sensitive,
                "info": item.card_info,
            }
        )
    return rows


def saved_listings(user):
    return base_queryset().filter(likes__user=user).order_by("-likes__created_at")


def owner_listings(user):
    return base_queryset().filter(owner=user).exclude(status=Listing.Status.ARCHIVED, title="")


def section_counts(location, viewer, enabled_slugs) -> dict[str, int]:
    """Live listings per section for the current campus/town (home page tiles)."""
    qs = for_location(visible_listings(viewer, enabled_slugs), location)
    rows = qs.order_by().values("section").annotate(n=Count("id", distinct=True))
    return {row["section"]: row["n"] for row in rows}
