"""DATA_SOURCES_PROMPT §19 — all offline against recorded responses."""

from datetime import timedelta
from pathlib import Path

import pytest
from constance import config
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.external import services
from apps.external.models import ExternalJob, ExternalSource, Place
from apps.locations.importers import http
from tests import factories as f

pytestmark = pytest.mark.django_db
FIX = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sources"
PLACES = http.load_json(FIX / "overpass_places.json")
JOBS = http.load_json(FIX / "remotive_jobs.json")


@pytest.fixture
def osm_source():
    return f.ExternalSourceFactory()


@pytest.fixture
def remotive():
    return f.ExternalSourceFactory(slug="remotive", kind="remotive_jobs", name="Remotive", min_interval_minutes=0,
                                   base_url="https://remotive.com/api/remote-jobs")


def run_places(source, campuses=None, data=PLACES):
    return services.run_source(source, fetcher=lambda campus: data)


def test_unapproved_source_never_runs(osm_source, campus, monkeypatch):
    osm_source.permission_status = "pending_review"
    osm_source.save()
    called = []
    with pytest.raises(services.SourceNotRunnable):
        services.run_source(osm_source, fetcher=lambda c: called.append(c) or PLACES)
    assert not called
    osm_source.permission_status = "approved"
    osm_source.enabled = False
    osm_source.save()
    assert services.run_due_sources() == []


def test_minimum_interval_enforced(osm_source, campus):
    run_places(osm_source)
    with pytest.raises(services.SourceNotRunnable, match="interval"):
        run_places(osm_source)


def test_tag_to_kind_mapping():
    assert services.kind_from_tags({"shop": "mobile_phone"}) == "phone_repair"
    assert services.kind_from_tags({"shop": "copyshop"}) == "copyshop"
    assert services.kind_from_tags({"shop": "dry_cleaning"}) == "laundry"
    assert services.kind_from_tags({"tourism": "guest_house"}) == "guest_house"
    assert services.kind_from_tags({"amenity": "bank"}) == "other"


def test_places_import_dedupes_across_campuses_and_phones_off(osm_source):
    a = f.CampusFactory(lat=7.3, lng=-2.3)
    b = f.CampusFactory(lat=7.31, lng=-2.31)
    run = run_places(osm_source)
    assert run.status == "ok" and run.created == 3  # nameless element skipped
    inn = Place.objects.get(source_id="node/8001")
    assert set(inn.campuses.all()) == {a, b}
    assert inn.phone == "" and not config.IMPORT_PLACE_PHONES
    assert inn.website == "https://inn.example.test"


def test_place_phones_imported_only_when_enabled(osm_source, campus):
    config.IMPORT_PLACE_PHONES = True
    run_places(osm_source)
    assert Place.objects.get(source_id="node/8001").phone
    config.IMPORT_PLACE_PHONES = False


def test_removed_after_two_missed_refreshes_claimed_untouched(osm_source, campus):
    run_places(osm_source)
    claimed = Place.objects.get(source_id="way/8002")
    claimed.status = "claimed"
    claimed.name = "Owner's Name"
    claimed.save()
    empty = {"elements": []}
    for _ in range(2):
        osm_source.last_run_at = timezone.now() - timedelta(days=1)
        osm_source.save()
        run_places(osm_source, data=empty)
    inn = Place.objects.get(source_id="node/8001")
    claimed.refresh_from_db()
    assert inn.status == "removed" and claimed.status == "claimed" and claimed.name == "Owner's Name"
    osm_source.last_run_at = None
    osm_source.save()
    run_places(osm_source)  # idempotent re-run brings back the unclaimed place, keeps the claim
    inn.refresh_from_db()
    claimed.refresh_from_db()
    assert inn.status == "unclaimed" and claimed.name == "Owner's Name"


def test_suspending_source_hides_content(client, osm_source, campus):
    run_places(osm_source)
    assert Place.objects.visible().count() == 3
    osm_source.permission_status = ExternalSource.Permission.SUSPENDED
    osm_source.save()
    assert Place.objects.visible().count() == 0
    assert client.get(reverse("around", args=[campus.slug])).content.count(b"Fixture Guest Inn") == 0


def test_places_appear_in_rooms_block_with_attribution_not_in_ranking(client, osm_source, campus):
    run_places(osm_source)
    html = client.get(reverse("listings:section_campus", args=[campus.slug, "rooms"])).content.decode()
    assert "Other places nearby" in html and "Fixture Guest Inn" in html
    assert "From OpenStreetMap — not verified, prices not listed." in html
    html = client.get(reverse("around", args=[campus.slug]) + "?tab=print").content.decode()
    assert "Fixture Print Shop" in html and "OpenStreetMap contributors" in html and "Claim this place" in html


def test_place_report_auto_hide(osm_source, campus):
    from apps.engagement.services import report

    run_places(osm_source)
    place = Place.objects.get(source_id="node/8001")
    for _ in range(3):
        report(f.UserFactory(), place, "closed")
    place.refresh_from_db()
    assert place.status == "hidden"


def test_claim_flow_accommodation_becomes_hostel(client, osm_source, campus):
    run_places(osm_source)
    place = Place.objects.get(source_id="node/8001")
    owner = f.UserFactory()
    client.force_login(owner)
    proof = SimpleUploadedFile("proof.jpg", b"\xff\xd8\xff fake", content_type="image/jpeg")
    client.post(reverse("external:claim", args=[place.slug]), {"proof_kind": "photo", "proof": proof})
    place.refresh_from_db()
    claim = place.claims.get()
    assert place.status == "claim_pending"
    storage, name = claim.proof.storage, claim.proof.name
    services.decide_claim(claim, True, f.UserFactory(is_staff=True))
    place.refresh_from_db()
    claim.refresh_from_db()
    assert place.status == "claimed" and place.owner == owner and place.hostel.owner == owner
    assert not storage.exists(name) and not claim.proof
    assert owner.notifications.filter(trigger="claim").exists()
    assert "Claimed by owner" in client.get(place.get_absolute_url()).content.decode()


def test_claim_rejected_notifies(osm_source, campus):
    run_places(osm_source)
    place = Place.objects.get(source_id="way/8002")
    user = f.UserFactory()
    claim = services.submit_claim(place, user, "registration", SimpleUploadedFile("r.pdf", b"%PDF-1"))
    services.decide_claim(claim, False, None, "Document unreadable")
    place.refresh_from_db()
    assert place.status == "unclaimed"
    assert user.notifications.get(trigger="claim").body == "Document unreadable"


def test_remotive_import_filters_and_never_stores_description(remotive):
    run = services.run_source(remotive, fetcher=lambda: JOBS)
    titles = set(ExternalJob.objects.values_list("title", flat=True))
    assert titles == {"Fixture Support Agent", "Fixture Writer"}, run.error
    assert not any("LONG DESCRIPTION" in str(v) for v in ExternalJob.objects.values())


def test_remotive_daily_cap_of_four_enforced(remotive):
    config.REMOTIVE_FETCHES_PER_DAY = 10  # admin typo — code clamps to 4
    now = timezone.now()
    for i in range(4):
        services.run_source(remotive, fetcher=lambda: JOBS, now=now + timedelta(hours=6 * i) - timedelta(hours=23))
    with pytest.raises(services.SourceNotRunnable):
        services.run_source(remotive, fetcher=lambda: JOBS, now=now)
    config.REMOTIVE_FETCHES_PER_DAY = 2


def test_remote_jobs_visible_to_guests_with_attribution(client, remotive, campus):
    services.run_source(remotive, fetcher=lambda: JOBS)
    html = client.get(reverse("listings:section_campus", args=[campus.slug, "jobs"]) + "?tab=remote").content.decode()
    assert "Fixture Writer" in html and "via Remotive" in html and "View and apply on Remotive" in html
    assert 'rel="noopener nofollow"' in html and "Remote jobs provided by" in html
    assert 'name="robots" content="noindex"' in html
    assert "JobPosting" not in html and "account_login" not in html and "Log in to" not in html


def test_external_jobs_absent_from_sitemaps_digest_alerts(client, remotive, campus):
    services.run_source(remotive, fetcher=lambda: JOBS)
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "remotive" not in sitemap.lower()
    from apps.growth.services import send_weekly_digest

    user = f.UserFactory()
    user.profile.home_campus = campus
    user.profile.save()
    send_weekly_digest()
    from django.core import mail

    assert all("Fixture Writer" not in m.body for m in mail.outbox)
    from apps.engagement.services import run_saved_search_alerts, save_search

    save_search(user, "jobs", {}, campus=campus)
    run_saved_search_alerts()
    assert not user.notifications.filter(title__icontains="Fixture Writer").exists()


def test_external_items_never_boostable_or_ranked():
    from apps.listings.models import Listing

    assert not hasattr(Place, "score") and not hasattr(ExternalJob, "score")
    assert "external" not in str(Listing._meta.get_fields())


def test_approval_requires_terms_review(osm_source):
    osm_source.permission_status = "pending_review"
    osm_source.terms_reviewed = False
    osm_source.save()
    with pytest.raises(ValueError):
        services.approve_source(osm_source, f.UserFactory(is_staff=True))
    osm_source.terms_reviewed = True
    services.approve_source(osm_source, f.UserFactory(is_staff=True))
    assert osm_source.permission_status == "approved"
