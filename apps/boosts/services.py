"""Free boosts with all limits (§5.6). No payment code: Boost.source is always 'free'."""

from __future__ import annotations

from datetime import timedelta

from constance import config
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Boost


class BoostRefused(Exception):
    pass


def boosts_used_this_week(user, now=None) -> int:
    now = now or timezone.now()
    return Boost.objects.filter(user=user, created_at__gte=now - timedelta(days=7), used_bonus=False).count()


def boosts_left(user, now=None) -> int:
    profile = getattr(user, "profile", None)
    bonus = profile.bonus_boosts if profile else 0
    return max(config.BOOSTS_PER_WEEK - boosts_used_this_week(user, now), 0) + bonus


def can_boost(user, listing=None, now=None):
    from apps.accounts.services import Decision, phone_required

    now = now or timezone.now()
    if user is None or not user.is_authenticated:
        return Decision(False, _("Log in first."))
    if not user.email_verified:
        return Decision(False, _("Verify your email address first."))
    if phone_required() and not user.phone_verified:
        return Decision(False, _("Verify your phone number to boost."))
    if (now - user.date_joined).total_seconds() / 3600 < config.BOOST_MIN_ACCOUNT_AGE_HOURS:
        return Decision(
            False,
            _("Accounts can boost after %(h)s hours.") % {"h": config.BOOST_MIN_ACCOUNT_AGE_HOURS},
        )
    if boosts_left(user, now) <= 0:
        return Decision(
            False,
            _("You've used your %(n)s free boosts for this week. Try again in a few days.")
            % {"n": config.BOOSTS_PER_WEEK},
        )
    if listing is not None:
        if listing.owner_id != user.pk:
            return Decision(False, _("You can only boost your own listings."))
        if listing.status != listing.Status.ACTIVE or listing.is_hidden:
            return Decision(False, _("Only active listings can be boosted."))
        if Boost.objects.active(now).filter(listing=listing).exists():
            return Decision(False, _("This listing is already boosted."))
    return Decision(True)


@transaction.atomic
def boost(user, listing, now=None) -> Boost:
    from apps.telemetry.services import record

    now = now or timezone.now()
    decision = can_boost(user, listing, now)
    if not decision:
        raise BoostRefused(decision.reason)
    use_bonus = boosts_used_this_week(user, now) >= config.BOOSTS_PER_WEEK
    if use_bonus:
        profile = user.profile
        profile.bonus_boosts = max(profile.bonus_boosts - 1, 0)
        profile.save(update_fields=["bonus_boosts"])
    item = Boost.objects.create(
        listing=listing,
        user=user,
        source=Boost.Source.FREE,
        starts_at=now,
        ends_at=now + timedelta(days=config.BOOST_DURATION_DAYS),
        used_bonus=use_bonus,
    )
    record("boost", user=user, listing=listing)
    return item


def end_boosts(listing, now=None) -> int:
    """Called when a listing becomes taken, expired or archived."""
    now = now or timezone.now()
    return Boost.objects.active(now).filter(listing=listing).update(ends_at=now)


def notify_ended(now=None) -> int:
    from apps.notifications.services import notify

    now = now or timezone.now()
    count = 0
    for item in Boost.objects.filter(ends_at__lte=now, end_notified=False).select_related("listing", "user"):
        notify(
            item.user,
            "boost_ended",
            _("Your boost on “%(title)s” has ended") % {"title": item.listing.title},
            url="/dashboard/",
        )
        item.end_notified = True
        item.save(update_fields=["end_notified"])
        count += 1
    return count
