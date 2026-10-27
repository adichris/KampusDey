"""Hostel Manager: room types own `rooms` listings; availability drives taken/active (§5.4)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.utils import unique_slug
from apps.listings.models import Listing, ListingCampus, RoomDetails

from .models import Hostel, HostelRoomType


class HostelError(Exception):
    pass


def can_manage_hostels(user) -> bool:
    profile = getattr(user, "profile", None)
    return bool(user.is_authenticated and profile and profile.role in ("landlord", "agent"))


@transaction.atomic
def sync_room_type_listing(room_type: HostelRoomType) -> Listing:
    """Create or update the `rooms` listing a room type owns."""
    hostel = room_type.hostel
    listing = room_type.listing
    title = f"{room_type.name} — {hostel.name}"
    if listing is None:
        listing = Listing(owner=hostel.owner, section="rooms", town=hostel.town, title=title)
        listing.slug = unique_slug(listing, title)
    listing.title = title
    listing.description = hostel.description
    listing.price = room_type.price
    listing.price_period = room_type.price_period
    listing.town = hostel.town
    listing.lat, listing.lng = hostel.lat, hostel.lng
    listing.contact_card = hostel.contact_card
    profile = getattr(hostel.owner, "profile", None)
    listing.seller_type = profile.effective_seller_type if profile else "business"
    new = listing.pk is None
    if new:
        listing.status = Listing.Status.ACTIVE
        listing.published_at = timezone.now()
        listing.approved_at = timezone.now()
    listing.save()
    RoomDetails.objects.update_or_create(
        listing=listing,
        defaults={
            "room_type": room_type.room_type,
            "gender": room_type.gender,
            "hostel_room_type": room_type,
            "wifi": "wifi" in (hostel.amenities or []),
            "security": "security" in (hostel.amenities or []),
            "kitchen": "kitchen" in (hostel.amenities or []),
        },
    )
    for campus in hostel.campuses.all():
        ListingCampus.objects.get_or_create(listing=listing, campus=campus, defaults={"is_manual": True})
    if hostel.lat is not None:
        from apps.listings.services import autolink_campuses

        autolink_campuses(listing)
    if new:
        room_type.listing = listing
        HostelRoomType.objects.filter(pk=room_type.pk).update(listing=listing)
    apply_availability(room_type)
    from apps.listings.services import update_search_vector

    update_search_vector(listing)
    return listing


def apply_availability(room_type: HostelRoomType) -> None:
    """0 available → linked listing `taken`; above 0 → back to `active`."""
    listing = room_type.listing
    if listing is None:
        return
    if room_type.available_rooms <= 0 and listing.status in Listing.VISIBLE_STATUSES:
        from apps.listings.services import mark_taken

        mark_taken(listing)
    elif room_type.available_rooms > 0 and listing.status == Listing.Status.TAKEN:
        listing.set_status(Listing.Status.ACTIVE)


def set_available(room_type: HostelRoomType, value: int) -> HostelRoomType:
    value = max(0, min(int(value), room_type.total_rooms))
    room_type.available_rooms = value
    room_type.save(update_fields=["available_rooms", "updated_at"])
    apply_availability(room_type)
    return room_type


def step_available(room_type: HostelRoomType, delta: int) -> HostelRoomType:
    return set_available(room_type, room_type.available_rooms + delta)


def create_hostel(owner, **data) -> Hostel:
    if not can_manage_hostels(owner):
        raise HostelError(_("Only landlords and agents can manage hostels."))
    hostel = Hostel(owner=owner, **data)
    hostel.slug = unique_slug(hostel, hostel.name)
    hostel.save()
    return hostel


def occupancy(hostel: Hostel) -> dict:
    totals = hostel.room_types.aggregate(total=Sum("total_rooms"), available=Sum("available_rooms"))
    total = totals["total"] or 0
    available = totals["available"] or 0
    return {
        "total": total,
        "available": available,
        "occupied": total - available,
        "pct": round(100 * (total - available) / total) if total else 0,
    }


def room_type_stats(hostel: Hostel):
    from django.db.models import Sum as S

    from apps.telemetry.models import DailyListingStats

    rows = []
    for rt in hostel.room_types.select_related("listing"):
        stats = {"views": 0, "taps": 0, "likes": 0}
        if rt.listing_id:
            agg = DailyListingStats.objects.filter(listing_id=rt.listing_id).aggregate(
                views=S("views"), taps=S("taps"), likes=S("likes")
            )
            stats = {k: v or 0 for k, v in agg.items()}
        rows.append({"room_type": rt, **stats})
    return rows


def inquiries(hostel: Hostel):
    from apps.chat.models import Conversation
    from apps.telemetry.models import Event

    listing_ids = list(hostel.room_types.exclude(listing=None).values_list("listing_id", flat=True))
    conversations = Conversation.objects.filter(listing_id__in=listing_ids).select_related("listing").order_by(
        "-last_message_at"
    )
    taps = Event.objects.filter(kind="tap", listing_id__in=listing_ids).order_by("-created_at")[:50]
    return conversations, taps
