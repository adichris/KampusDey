"""Listing business rules: drafts, publishing, location, campus links, lifecycle, ranking."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from constance import config
from django.core import signing
from django.db import connection, transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import geo
from apps.core.images import clean_image
from apps.core.utils import absolute_url, unique_slug
from apps.locations.models import Campus

from .models import Listing, ListingCampus, ListingPhoto
from .sections import SECTIONS

logger = logging.getLogger(__name__)
CHECK_SALT = "kd.listing.check"
CHECK_MAX_AGE = 60 * 60 * 24 * 21
TIME_BOUND_SECTIONS = {"food", "events", "alerts", "errands", "trips"}


class ListingError(Exception):
    pass


# ---------------------------------------------------------------------------
# Drafts and details
# ---------------------------------------------------------------------------
def create_draft(owner, section: str, location) -> Listing:
    if section not in SECTIONS:
        raise ListingError(_("Unknown section."))
    town = location.effective_town
    if town is None:
        raise ListingError(_("Choose your campus or town first."))
    listing = Listing(owner=owner, section=section, town=town, title=_("Untitled draft"))
    listing.slug = unique_slug(listing, f"{section}-draft")
    if location.campus and location.campus.has_point:
        listing.lat, listing.lng = geo.snap(*location.campus.point, config.LOCATION_SNAP_M)
    listing.save()
    if location.campus:
        ListingCampus.objects.get_or_create(
            listing=listing, campus=location.campus, defaults={"is_manual": True}
        )
    from apps.contacts.services import default_card

    listing.contact_card = default_card(owner)
    listing.save(update_fields=["contact_card"])
    return listing


def set_point(listing: Listing, lat, lng) -> None:
    """Store only a snapped point (§6.3)."""
    if lat in (None, "") or lng in (None, ""):
        return
    lat, lng = float(lat), float(lng)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ListingError(_("Invalid map position."))
    listing.lat, listing.lng = geo.snap(lat, lng, config.LOCATION_SNAP_M)


def autolink_campuses(listing: Listing) -> list[ListingCampus]:
    """Link campuses within CAMPUS_AUTOLINK_RADIUS_M; keep manual links and exclusions."""
    existing = {link.campus_id: link for link in listing.campus_links.all()}
    if listing.has_point:
        found = geo.nearby(
            Campus.objects.visible().with_point(),
            listing.lat,
            listing.lng,
            config.CAMPUS_AUTOLINK_RADIUS_M,
        )
        found_ids = set()
        for campus in found:
            found_ids.add(campus.pk)
            dist = int(campus.distance_m)
            link = existing.get(campus.pk)
            if link is None:
                ListingCampus.objects.create(listing=listing, campus=campus, distance_m=dist)
            elif link.distance_m != dist:
                link.distance_m = dist
                link.save(update_fields=["distance_m"])
        # Automatic links that are now out of range go away; manual ones stay.
        for campus_id, link in existing.items():
            if campus_id not in found_ids and not link.is_manual and not link.is_excluded:
                link.delete()
    return list(listing.campus_links.select_related("campus"))


def update_campus_links(listing: Listing, keep_ids, add_ids):
    """User edits on step 3: untick auto-linked campuses or add others."""
    keep_ids = {int(i) for i in keep_ids or []}
    for link in listing.campus_links.all():
        excluded = link.campus_id not in keep_ids
        if link.is_excluded != excluded:
            link.is_excluded = excluded
            link.save(update_fields=["is_excluded"])
    for cid in add_ids or []:
        campus = Campus.objects.visible().filter(pk=cid).first()
        if campus:
            dist = None
            if listing.has_point and campus.has_point:
                dist = int(geo.haversine_m(listing.lat, listing.lng, campus.lat, campus.lng))
            ListingCampus.objects.update_or_create(
                listing=listing,
                campus=campus,
                defaults={"is_manual": True, "is_excluded": False, "distance_m": dist},
            )


def save_details(listing: Listing, details_form) -> None:
    details = details_form.save(commit=False)
    details.listing = listing
    details.save()
    details_form.save_m2m()
    listing.__dict__.pop("details", None)


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------
def add_photo(listing: Listing, upload) -> ListingPhoto:
    if listing.photos.count() >= config.MAX_PHOTOS:
        raise ListingError(_("You can add up to %(n)s photos.") % {"n": config.MAX_PHOTOS})
    from django.core.exceptions import ValidationError

    try:
        content, width, height, phash = clean_image(upload, config.MAX_UPLOAD_MB)
    except ValidationError as exc:
        raise ListingError(" ".join(exc.messages))
    from apps.moderation.services import photo_is_duplicate

    if photo_is_duplicate(listing, phash):
        raise ListingError(_("You already posted this photo on another listing."))
    order = (listing.photos.order_by("-order").values_list("order", flat=True).first() or 0) + 1
    photo = ListingPhoto(listing=listing, order=order, phash=phash)
    photo.image.save(content.name, content, save=False)
    photo.width, photo.height = width, height
    photo.save()
    return photo


def reorder_photos(listing: Listing, ids: list) -> None:
    photos = {p.pk: p for p in listing.photos.all()}
    for position, pid in enumerate(ids, start=1):
        photo = photos.get(int(pid))
        if photo and photo.order != position:
            photo.order = position
            photo.save(update_fields=["order"])


def delete_photos(listing: Listing) -> int:
    count = 0
    for photo in listing.photos.all():
        photo.image.delete(save=False)
        photo.delete()
        count += 1
    return count


# ---------------------------------------------------------------------------
# Publishing and status
# ---------------------------------------------------------------------------
def approved_post_count(user) -> int:
    return Listing.objects.filter(owner=user, approved_at__isnull=False).count()


def compute_expires_at(listing: Listing):
    base = listing.confirmed_at or listing.published_at or timezone.now()
    days = section_threshold(listing.section, "expire")
    expires = base + timedelta(days=days)
    field = listing.section_obj.expiry_field
    details = listing.details
    if field and details is not None:
        value = getattr(details, field, None)
        if field == "ends_at" and value is None:
            value = details.starts_at + timedelta(hours=12)
        if value is not None:
            if not hasattr(value, "hour"):
                value = timezone.make_aware(datetime(value.year, value.month, value.day, 23, 59))
            expires = min(expires, value)
    return expires


@transaction.atomic
def publish(listing: Listing, request=None) -> Listing:
    """Run moderation, then make the listing active or send it to review."""
    from apps.moderation.services import ModerationBlocked, check_listing

    if listing.status not in (Listing.Status.DRAFT, Listing.Status.PENDING_REVIEW):
        return listing
    if not listing.title or listing.title == _("Untitled draft"):
        raise ListingError(_("Add a title."))
    validate_section_rules(listing)
    verdict = check_listing(listing)
    if verdict.blocked:
        raise ModerationBlocked(verdict.message)
    profile = getattr(listing.owner, "profile", None)
    listing.seller_type = profile.effective_seller_type if profile else ""
    listing.published_at = listing.published_at or timezone.now()
    listing.expires_at = compute_expires_at(listing)
    needs_review = (
        verdict.review or approved_post_count(listing.owner) < config.NEW_SELLER_REVIEW_COUNT
    )
    if needs_review:
        listing.status = Listing.Status.PENDING_REVIEW
    else:
        listing.status = Listing.Status.ACTIVE
        listing.approved_at = timezone.now()
    listing.status_changed_at = timezone.now()
    listing.slug = unique_slug(listing, listing.title)
    listing.save()
    if needs_review:
        from apps.moderation.services import queue_for_review

        queue_for_review(listing, verdict.reason or _("New seller: first posts are reviewed"))
    autolink_campuses(listing)
    update_search_vector(listing)
    listing.score = compute_score(listing)
    listing.save(update_fields=["score"])
    from apps.growth.services import maybe_reward_referral
    from apps.telemetry.services import record

    record("post", request=request, user=listing.owner, listing=listing)
    transaction.on_commit(lambda: maybe_reward_referral(listing.owner))
    return listing


def validate_section_rules(listing: Listing):
    section = listing.section_obj
    if listing.price is not None and listing.price < 0:
        raise ListingError(_("Price cannot be negative."))
    if not section.price_allowed and listing.price not in (None, 0):
        if listing.section == "food":
            raise ListingError(_("Food posts cannot have a price."))
        listing.price = None
    if listing.section == "free-leaving":
        listing.is_free = True
        listing.price = None
    if listing.section == "food":
        details = listing.details
        if details is None:
            raise ListingError(_("Add the food details."))
        max_until = timezone.now() + timedelta(hours=config.FOOD_POST_MAX_HOURS)
        if details.available_until > max_until:
            details.available_until = max_until
            details.save(update_fields=["available_until"])
        if details.post_kind == "need_food":
            listing.contact_visibility = Listing.Visibility.MEMBERS


def approve(listing: Listing) -> None:
    listing.status = Listing.Status.ACTIVE
    listing.approved_at = listing.approved_at or timezone.now()
    listing.is_hidden = False
    listing.hidden_reason = ""
    listing.status_changed_at = timezone.now()
    listing.save()


def mark_taken(listing: Listing) -> None:
    from apps.boosts.services import end_boosts

    listing.set_status(Listing.Status.TAKEN)
    end_boosts(listing)


def confirm_available(listing: Listing) -> None:
    """'Still available' answer or one-tap renew: resets the lifecycle clock."""
    now = timezone.now()
    listing.confirmed_at = now
    listing.needs_check_sent_at = None
    if listing.status in (Listing.Status.NEEDS_CHECK, Listing.Status.EXPIRED, Listing.Status.TAKEN):
        listing.status = Listing.Status.ACTIVE
        listing.status_changed_at = now
    listing.expires_at = compute_expires_at(listing)
    listing.save()


def archive(listing: Listing) -> None:
    from apps.boosts.services import end_boosts

    delete_photos(listing)
    listing.set_status(Listing.Status.ARCHIVED)
    end_boosts(listing)


def check_token(listing: Listing, action: str) -> str:
    return signing.dumps({"l": listing.pk, "a": action}, salt=CHECK_SALT)


def check_url(listing: Listing, action: str) -> str:
    return absolute_url(reverse("listings:one_tap", args=[check_token(listing, action)]))


def read_check_token(token: str):
    data = signing.loads(token, salt=CHECK_SALT, max_age=CHECK_MAX_AGE)
    return Listing.objects.get(pk=data["l"]), data["a"]


# ---------------------------------------------------------------------------
# Lifecycle (§6.6)
# ---------------------------------------------------------------------------
def section_threshold(section: str, key: str) -> int:
    defaults = {
        "needs_check": config.EXPIRY_NEEDS_CHECK_DAYS,
        "expire": config.EXPIRY_EXPIRE_DAYS,
        "archive": config.EXPIRY_ARCHIVE_DAYS,
    }
    overrides = config.SECTION_EXPIRY_OVERRIDES or {}
    if isinstance(overrides, str):
        import json

        try:
            overrides = json.loads(overrides)
        except ValueError:
            overrides = {}
    value = (overrides.get(section) or {}).get(key)
    return int(value) if value else defaults[key]


def _age_days(listing: Listing, now) -> float:
    base = listing.confirmed_at or listing.published_at or listing.created_at
    return (now - base).total_seconds() / 86400


def run_lifecycle(now=None) -> dict:
    """Idempotent: each transition only applies when the listing is in the prior state."""
    from apps.boosts.services import end_boosts
    from apps.notifications.services import notify

    now = now or timezone.now()
    stats = {"needs_check": 0, "expired": 0, "archived": 0, "detail_expired": 0}

    live = Listing.objects.filter(status__in=Listing.VISIBLE_STATUSES).select_related("owner")
    for listing in live.iterator():
        field = listing.section_obj.expiry_field
        if field and listing.expires_at and listing.expires_at <= now:
            listing.set_status(Listing.Status.EXPIRED)
            end_boosts(listing)
            stats["detail_expired"] += 1
            continue
        age = _age_days(listing, now)
        if age >= section_threshold(listing.section, "expire"):
            listing.set_status(Listing.Status.EXPIRED)
            end_boosts(listing)
            stats["expired"] += 1
        elif (
            listing.status == Listing.Status.ACTIVE
            and age >= section_threshold(listing.section, "needs_check")
            and listing.section not in TIME_BOUND_SECTIONS
        ):
            listing.status = Listing.Status.NEEDS_CHECK
            listing.status_changed_at = now
            listing.needs_check_sent_at = now
            listing.save(
                update_fields=["status", "status_changed_at", "needs_check_sent_at", "updated_at"]
            )
            notify(
                listing.owner,
                "still_available",
                _("Is “%(title)s” still available?") % {"title": listing.title},
                _("Tap to confirm, or mark it as taken."),
                url=reverse("listings:check", args=[listing.slug]),
                extra={
                    "confirm_url": check_url(listing, "confirm"),
                    "taken_url": check_url(listing, "taken"),
                },
            )
            stats["needs_check"] += 1

    old = Listing.objects.filter(status__in=[Listing.Status.EXPIRED, Listing.Status.TAKEN])
    for listing in old.iterator():
        if _age_days(listing, now) >= section_threshold(listing.section, "archive"):
            archive(listing)
            stats["archived"] += 1
    return stats


# ---------------------------------------------------------------------------
# Ranking (§6.4)
# ---------------------------------------------------------------------------
def compute_score(listing: Listing, now=None, photo_count=None, owner_verified=None) -> float:
    now = now or timezone.now()
    base = listing.published_at or listing.created_at or now
    age_days = max((now - base).total_seconds() / 86400, 0)
    fresh = math.exp(-age_days / max(config.FRESH_HALF_LIFE_DAYS, 0.1))
    activity = min(
        math.log1p(3 * listing.taps_7d + 2 * listing.likes_7d + 0.2 * listing.views_7d),
        config.ACTIVITY_CAP,
    )
    if photo_count is None:
        photo_count = listing.photos.count()
    if owner_verified is None:
        profile = getattr(listing.owner, "profile", None)
        owner_verified = bool(profile and profile.is_verified)
    quality = (1 if photo_count >= 3 else 0) + (1 if owner_verified else 0)
    return (
        config.W_FRESH * fresh
        + config.W_ACT * activity
        + config.W_QUAL * quality
        - config.W_REPORT * listing.reports_count
    )


def recompute_scores() -> int:
    now = timezone.now()
    qs = (
        Listing.objects.filter(status__in=Listing.VISIBLE_STATUSES)
        .select_related("owner__profile")
        .annotate(n_photos=Count("photos"))
    )
    batch = []
    for listing in qs.iterator(chunk_size=500):
        profile = getattr(listing.owner, "profile", None)
        listing.score = compute_score(
            listing,
            now,
            photo_count=listing.n_photos,
            owner_verified=bool(profile and profile.is_verified),
        )
        batch.append(listing)
        if len(batch) >= 500:
            Listing.objects.bulk_update(batch, ["score"])
            batch = []
    if batch:
        Listing.objects.bulk_update(batch, ["score"])
    return qs.count()


def update_search_vector(listing: Listing) -> None:
    if connection.vendor != "postgresql":
        return
    from django.contrib.postgres.search import SearchVector

    Listing.objects.filter(pk=listing.pk).update(
        search_vector=SearchVector("title", weight="A", config="english")
        + SearchVector("description", weight="B", config="english")
    )


def visible_q() -> Q:
    return Q(status__in=Listing.VISIBLE_STATUSES, is_hidden=False)
