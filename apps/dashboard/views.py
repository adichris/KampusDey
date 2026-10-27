"""Poster dashboard: listings, statuses, renew, mark taken, boosts and stats (§6.6, §6.12)."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.boosts.services import BoostRefused, boost, boosts_left
from apps.listings import services as listing_services
from apps.listings.models import Listing
from apps.telemetry.models import DailyListingStats

from .selectors import listing_stats


@login_required
def home(request):
    listings = (
        Listing.objects.filter(owner=request.user)
        .exclude(status=Listing.Status.ARCHIVED, photos__isnull=True, title="")
        .prefetch_related("photos", "boosts")
        .order_by("-updated_at")
    )
    status = request.GET.get("status")
    if status:
        listings = listings.filter(status=status)
    since = timezone.localdate() - timedelta(days=7)
    week = DailyListingStats.objects.filter(listing__owner=request.user, date__gte=since).aggregate(
        views=Sum("views"),
        taps=Sum("taps"),
        likes=Sum("likes"),
        shares=Sum("shares"),
        comments=Sum("comments"),
    )
    now = timezone.now()
    for item in listings:
        item.active_boost = next(
            (b for b in item.boosts.all() if b.starts_at <= now < b.ends_at), None
        )
    return render(
        request,
        "dashboard/home.html",
        {
            "listings": listings,
            "week": {k: v or 0 for k, v in week.items()},
            "boosts_left": boosts_left(request.user),
            "statuses": Listing.Status.choices,
            "active_status": status,
        },
    )


@login_required
def stats(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    return render(request, "dashboard/stats.html", {"listing": listing, **listing_stats(listing)})


@login_required
@require_POST
def renew(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if listing.status == Listing.Status.ARCHIVED:
        messages.error(request, _("Archived listings can't be restored. Post it again."))
    else:
        listing_services.confirm_available(listing)
        messages.success(request, _("Renewed. Your listing is back up."))
    return redirect("dashboard:home")


@login_required
@require_POST
def taken(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    listing_services.mark_taken(listing)
    messages.success(request, _("Marked as taken."))
    return redirect("dashboard:home")


@login_required
@require_POST
def boost_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    try:
        boost(request.user, listing)
        messages.success(request, _("Boosted! Your listing shows in boosted slots for a few days."))
    except BoostRefused as exc:
        messages.error(request, str(exc))
    return redirect(request.POST.get("next") or "dashboard:home")
