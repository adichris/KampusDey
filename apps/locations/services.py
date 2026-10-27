"""Location context, picker helpers, nearest campuses, GeoIP hint, campus requests."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.core import geo

from .models import Campus, CampusKind, CampusRequest, Region, Source, Town

logger = logging.getLogger(__name__)
COOKIE_NAME = "kd_loc"
COOKIE_SALT = "kd.location"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365


@dataclass
class LocationContext:
    campus: Campus | None = None
    town: Town | None = None

    @property
    def is_set(self) -> bool:
        return bool(self.campus or self.town)

    @property
    def point(self):
        if self.campus and self.campus.has_point:
            return self.campus.point
        town = self.effective_town
        if town and town.has_point:
            return town.point
        return None

    @property
    def effective_town(self):
        return self.town or (self.campus.town if self.campus else None)

    @property
    def label(self):
        if self.campus:
            return self.campus.label
        if self.town:
            return self.town.name
        return _("Choose location")


def encode_choice(campus=None, town=None) -> str:
    if campus:
        return f"c:{campus.pk}"
    if town:
        return f"t:{town.pk}"
    return ""


def decode_choice(value: str | None) -> LocationContext:
    ctx = LocationContext()
    if not value or ":" not in value:
        return ctx
    kind, _sep, pk = value.partition(":")
    if not pk.isdigit():
        return ctx
    if kind == "c":
        ctx.campus = Campus.objects.visible().select_related("town__region").filter(pk=pk).first()
    elif kind == "t":
        ctx.town = Town.objects.select_related("region").filter(pk=pk).first()
    return ctx


def resolve_location(request) -> LocationContext:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        profile = getattr(user, "profile", None)
        if profile and (profile.home_campus_id or profile.home_town_id):
            campus = profile.home_campus
            if campus and campus.is_active:
                return LocationContext(campus=campus)
            if profile.home_town_id:
                return LocationContext(town=profile.home_town)
    raw = request.get_signed_cookie(COOKIE_NAME, default=None, salt=COOKIE_SALT)
    return decode_choice(raw)


def set_location(request, response, campus=None, town=None):
    """Persist the choice: signed cookie for everyone, Profile for logged-in users."""
    value = encode_choice(campus, town)
    response.set_signed_cookie(
        COOKIE_NAME, value, salt=COOKIE_SALT, max_age=COOKIE_MAX_AGE, samesite="Lax", httponly=True
    )
    user = request.user
    if user.is_authenticated:
        from apps.accounts.services import ensure_profile

        profile = ensure_profile(user)
        profile.home_campus = campus
        profile.home_town = town if not campus else campus.town
        profile.save(update_fields=["home_campus", "home_town", "updated_at"])
        if campus:
            profile.followed_campuses.add(campus)
    return response


def adopt_guest_location(request, user):
    from apps.accounts.services import ensure_profile

    profile = ensure_profile(user)
    if profile.home_campus_id or profile.home_town_id:
        return
    raw = request.get_signed_cookie(COOKIE_NAME, default=None, salt=COOKIE_SALT)
    ctx = decode_choice(raw)
    if ctx.is_set:
        profile.home_campus = ctx.campus
        profile.home_town = ctx.effective_town
        profile.save(update_fields=["home_campus", "home_town", "updated_at"])


def campuses_by_region(query: str = ""):
    qs = (
        Campus.objects.visible()
        .select_related("town__region")
        .order_by("town__region__name", "name")
    )
    if query:
        from django.db.models import Q

        qs = qs.filter(
            Q(name__icontains=query)
            | Q(short_name__icontains=query)
            | Q(town__name__icontains=query)
        )
    groups: dict[str, list[Campus]] = {}
    for campus in qs[:300]:
        groups.setdefault(campus.town.region.name, []).append(campus)
    return groups


def nearest_campuses(lat: float, lng: float, limit: int = 5):
    """Nearest visible campuses with a point (straight-line distance)."""
    qs = Campus.objects.visible().with_point().select_related("town__region")
    qs = geo.annotate_distance(qs, lat, lng).order_by("distance_m")
    return list(qs[:limit])


def campuses_within(lat: float, lng: float, radius_m: float):
    qs = Campus.objects.visible().with_point()
    return list(geo.nearby(qs, lat, lng, radius_m).order_by("distance_m"))


def region_for_point(lat: float, lng: float) -> Region | None:
    candidates = Region.objects.filter(
        boundary__isnull=False,
        min_lat__lte=lat,
        max_lat__gte=lat,
        min_lng__lte=lng,
        max_lng__gte=lng,
    )
    for region in candidates:
        if geo.geometry_contains(region.boundary, lat, lng):
            return region
    return None


# ---------------------------------------------------------------------------
# GeoIP hint (region only, never auto-selected, never for ranking/nearby)
# ---------------------------------------------------------------------------
def geoip_region_hint(request) -> Region | None:
    from apps.core.utils import get_client_ip

    path = Path(settings.GEOIP_PATH) / "GeoLite2-City.mmdb"
    if not path.exists():
        return None
    try:
        import geoip2.database  # optional dependency
    except ImportError:
        return None
    ip = get_client_ip(request)
    if not ip:
        return None
    try:
        with geoip2.database.Reader(str(path)) as reader:
            resp = reader.city(ip)
    except Exception:  # address not found, corrupt db, private IP…
        return None
    if resp.country.iso_code != "GH":
        return None
    name = (resp.subdivisions.most_specific.name or "").replace(" Region", "").strip()
    if not name:
        return None
    return Region.objects.filter(name__iexact=name).first()


# ---------------------------------------------------------------------------
# Campus requests
# ---------------------------------------------------------------------------
@transaction.atomic
def approve_campus_request(req: CampusRequest) -> Campus:
    from apps.notifications.services import notify

    from .classify import classify_kind

    town = Town.objects.filter(name__iexact=req.town_name, region=req.region).first()
    if town is None:
        town = Town.objects.create(
            region=req.region,
            name=req.town_name,
            slug=_unique_slug(Town, f"{req.town_name}-{req.region.slug}"),
            source=Source.MANUAL,
        )
    campus = Campus.objects.create(
        town=town,
        name=req.name,
        slug=_unique_slug(Campus, req.name),
        kind=classify_kind(req.name) or CampusKind.OTHER,
        source=Source.MANUAL,
        confidence=0.5,
    )
    req.status = CampusRequest.Status.ADDED
    req.created_campus = campus
    req.save(update_fields=["status", "created_campus", "updated_at"])
    if req.requester:
        notify(
            req.requester,
            "campus_request",
            _("%(name)s is now on KampusDey") % {"name": campus.name},
            url=campus.get_absolute_url(),
        )
    return campus


def reject_campus_request(req: CampusRequest):
    from apps.notifications.services import notify

    req.status = CampusRequest.Status.REJECTED
    req.save(update_fields=["status", "updated_at"])
    if req.requester:
        notify(
            req.requester, "campus_request", _("We couldn't add %(name)s yet") % {"name": req.name}
        )


def _unique_slug(model, value):
    base = slugify(value)[:150] or "item"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


unique_slug = _unique_slug
