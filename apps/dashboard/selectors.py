from collections import Counter
from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone

from apps.telemetry.models import DailyListingStats, Event


def listing_stats(listing) -> dict:
    """Per-listing totals and per-week rows (views, taps by channel, likes, shares, comments)."""
    rows = (
        DailyListingStats.objects.filter(listing=listing)
        .annotate(week=TruncWeek("date"))
        .values("week")
        .annotate(
            views=Sum("views"),
            taps=Sum("taps"),
            likes=Sum("likes"),
            shares=Sum("shares"),
            comments=Sum("comments"),
        )
        .order_by("-week")[:12]
    )
    channels = Counter()
    for item in DailyListingStats.objects.filter(listing=listing).values_list(
        "taps_by_channel", flat=True
    ):
        channels.update(item or {})
    # Today's not-yet-rolled-up events, so new listings see numbers immediately.
    today_start = timezone.now() - timedelta(hours=24)
    live = Counter(
        Event.objects.filter(listing=listing, created_at__gte=today_start).values_list(
            "kind", flat=True
        )
    )
    totals = DailyListingStats.objects.filter(listing=listing).aggregate(
        views=Sum("views"),
        taps=Sum("taps"),
        likes=Sum("likes"),
        shares=Sum("shares"),
        comments=Sum("comments"),
    )
    return {
        "weeks": list(rows),
        "channels": dict(channels),
        "totals": {k: v or 0 for k, v in totals.items()},
        "last_24h": dict(live),
    }
