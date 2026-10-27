"""Ambassadors and referrals, weekly digest, rent check, spotlight (§6.13)."""

from __future__ import annotations

import secrets
import statistics
from datetime import timedelta

from constance import config
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Referral, Spotlight

REF_SESSION_KEY = "kd_ref"


def ensure_referral_code(profile) -> str:
    if not profile.referral_code:
        while True:
            code = secrets.token_urlsafe(6)[:8].replace("-", "x").replace("_", "y")
            if not type(profile).objects.filter(referral_code=code).exists():
                break
        profile.referral_code = code
        profile.save(update_fields=["referral_code"])
    return profile.referral_code


def attach_referral(request, user) -> Referral | None:
    from apps.accounts.models import Profile

    code = request.session.pop(REF_SESSION_KEY, None) if request is not None else None
    if not code:
        return None
    ambassador_profile = (
        Profile.objects.filter(referral_code=code, is_ambassador=True)
        .select_related("user")
        .first()
    )
    if ambassador_profile is None or ambassador_profile.user_id == user.pk:
        return None
    referral, _created = Referral.objects.get_or_create(
        referred_user=user, defaults={"ambassador": ambassador_profile.user}
    )
    return referral


@transaction.atomic
def maybe_reward_referral(user) -> bool:
    """Credit the ambassador once the referred user has a verified email and a first post."""
    from apps.listings.models import Listing
    from apps.notifications.services import notify

    referral = (
        Referral.objects.select_for_update().filter(referred_user=user, rewarded=False).first()
    )
    if referral is None:
        return False
    if not user.email_verified:
        return False
    if not Listing.objects.filter(owner=user, published_at__isnull=False).exists():
        return False
    profile = referral.ambassador.profile
    profile.bonus_boosts += config.AMBASSADOR_BONUS_BOOSTS
    profile.save(update_fields=["bonus_boosts"])
    referral.rewarded = True
    referral.save(update_fields=["rewarded", "updated_at"])
    notify(
        referral.ambassador,
        "referral",
        _("You earned %(n)s extra boosts") % {"n": config.AMBASSADOR_BONUS_BOOSTS},
        _("Someone you invited just made their first post."),
        url="/dashboard/",
    )
    return True


def rent_check(campus) -> dict:
    """Median and range of rent by area and room type from KampusDey's own listings only."""
    from apps.listings.models import Listing

    since = timezone.now() - timedelta(days=180)
    qs = (
        Listing.objects.filter(
            section="rooms",
            campus_links__campus=campus,
            campus_links__is_excluded=False,
            price__isnull=False,
            price__gt=0,
            price_period="per_year",
        )
        .filter(
            status__in=[Listing.Status.ACTIVE, Listing.Status.NEEDS_CHECK, Listing.Status.TAKEN],
            updated_at__gte=since,
        )
        .select_related("area", "roomdetails")
    )
    groups: dict[tuple, list] = {}
    for listing in qs.distinct():
        details = listing.details
        room_type = details.get_room_type_display() if details else _("Room")
        area = listing.area.name if listing.area_id else _("Around campus")
        groups.setdefault((area, room_type), []).append(listing.price)
    min_samples = config.RENT_CHECK_MIN_SAMPLES
    rows = []
    for (area, room_type), prices in sorted(groups.items()):
        rows.append(
            {
                "area": area,
                "room_type": room_type,
                "count": len(prices),
                "enough": len(prices) >= min_samples,
                "median": statistics.median(prices) if len(prices) >= min_samples else None,
                "low": min(prices) if len(prices) >= min_samples else None,
                "high": max(prices) if len(prices) >= min_samples else None,
            }
        )
    return {"rows": rows, "min_samples": min_samples, "period": _("per year")}


def current_spotlight(campus=None):
    week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    qs = Spotlight.objects.filter(
        week_start__lte=week_start, week_start__gt=week_start - timedelta(days=7)
    )
    if campus is not None:
        item = qs.filter(campus=campus).select_related("listing", "user").first()
        if item:
            return item
    return qs.filter(campus__isnull=True).select_related("listing", "user").first()


def send_weekly_digest(now=None) -> int:
    """Weekly 'new near you' digest (opt-out). Remote/external jobs are never included."""
    from apps.accounts.models import User
    from apps.listings.selectors import for_campus, for_town, visible_listings

    now = now or timezone.now()
    since = now - timedelta(days=7)
    sent = 0
    users = User.objects.filter(is_active=True, is_anonymised=False).select_related(
        "profile__home_campus", "profile__home_town", "notification_prefs"
    )
    for user in users.iterator():
        prefs = getattr(user, "notification_prefs", None)
        if prefs is not None and not prefs.weekly_digest:
            continue
        profile = getattr(user, "profile", None)
        if not profile or not (profile.home_campus_id or profile.home_town_id):
            continue
        qs = visible_listings(user).filter(published_at__gte=since).exclude(owner=user)
        qs = (
            for_campus(qs, profile.home_campus)
            if profile.home_campus_id
            else for_town(qs, profile.home_town)
        )
        items = list(qs.order_by("-score")[:8])
        if not items:
            continue
        ctx = {
            "user": user,
            "items": items,
            "SITE_URL": settings.SITE_URL,
            "place": profile.home_campus or profile.home_town,
        }
        msg = EmailMultiAlternatives(
            _("[KampusDey] New near you this week"),
            render_to_string("emails/digest.txt", ctx),
            to=[user.email],
        )
        msg.attach_alternative(render_to_string("emails/digest.html", ctx), "text/html")
        msg.send()
        sent += 1
    return sent
