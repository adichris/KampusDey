from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.telemetry import services
from apps.telemetry.models import DailyCampusStats, DailyListingStats, Event, PendingEvent
from tests import factories as f

pytestmark = pytest.mark.django_db
UA = "Mozilla/5.0 (Linux; Android 13) Mobile"


def test_repeated_views_count_once(client):
    listing = f.ListingFactory()
    for _ in range(3):
        client.get(listing.get_absolute_url(), HTTP_USER_AGENT=UA)
    services.flush()
    assert Event.objects.filter(kind="view", listing=listing).count() == 1


def test_bots_are_ignored(client):
    listing = f.ListingFactory()
    client.get(listing.get_absolute_url(), HTTP_USER_AGENT="Googlebot/2.1")
    services.flush()
    assert not Event.objects.filter(kind="view").exists()


def test_buffer_then_flush_bulk_creates():
    listing = f.ListingFactory()
    services.record("tap", listing=listing, meta={"channel": "whatsapp"})
    assert PendingEvent.objects.count() == 1 and not Event.objects.exists()
    assert services.flush() == 1
    assert not PendingEvent.objects.exists() and Event.objects.get().meta["channel"] == "whatsapp"


def test_no_ip_addresses_in_telemetry_tables(client):
    listing = f.ListingFactory()
    client.get(listing.get_absolute_url(), HTTP_USER_AGENT=UA, REMOTE_ADDR="203.0.113.77")
    services.flush()
    for model in (Event, DailyListingStats, DailyCampusStats, PendingEvent):
        columns = [f.name for f in model._meta.get_fields()]
        assert not any(c == "ip" or c.endswith("_ip") or "address" in c for c in columns)
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM telemetry_event")
        assert "203.0.113.77" not in str(cur.fetchall())


def test_rollup_daily_stats_and_counters(campus):
    listing = f.ListingFactory()
    yesterday = timezone.now() - timedelta(days=1)
    for kind, meta in [
        ("view", {}),
        ("view", {}),
        ("tap", {"channel": "phone"}),
        ("like", {}),
        ("share", {}),
    ]:
        f.EventFactory(kind=kind, listing=listing, meta=meta, created_at=yesterday, campus=campus)
    f.EventFactory(
        kind="search", meta={"query": "x", "results": 0}, campus=campus, created_at=yesterday
    )
    services.rollup(timezone.localdate(yesterday))
    stats = DailyListingStats.objects.get(listing=listing)
    assert (stats.views, stats.taps, stats.likes, stats.shares) == (2, 1, 1, 1)
    assert stats.taps_by_channel == {"phone": 1}
    cstats = DailyCampusStats.objects.get(campus=campus)
    assert cstats.searches == 1 and cstats.zero_result_searches == 1 and cstats.views == 2
    listing.refresh_from_db()
    assert listing.views_7d == 2 and listing.taps_7d == 1
    services.rollup(timezone.localdate(yesterday))  # idempotent
    assert DailyListingStats.objects.get(listing=listing).views == 2


def test_raw_retention_cleanup():
    f.EventFactory(created_at=timezone.now() - timedelta(days=91))
    f.EventFactory()
    assert services.cleanup_raw() == 1 and Event.objects.count() == 1
