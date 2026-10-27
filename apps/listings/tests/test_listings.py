import io
import math
from datetime import timedelta

import pytest
import time_machine
from constance import config
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.listings import selectors, services
from apps.listings.models import Listing, ListingCampus
from apps.listings.sections import SECTIONS
from apps.locations.services import LocationContext
from apps.sitesettings.models import SectionAvailability
from tests import factories as f

pytestmark = pytest.mark.django_db


def _jpeg(color="blue", exif=True):
    img = Image.new("RGB", (120, 90), color)
    buf = io.BytesIO()
    ex = Image.Exif()
    ex[0x010F] = "Cam"
    img.save(buf, format="JPEG", exif=ex if exif else b"")
    return SimpleUploadedFile("p.jpg", buf.getvalue(), content_type="image/jpeg")


def _approved_seller():
    user = f.UserFactory()
    f.ListingFactory.create_batch(3, owner=user, section="services", approved_at=timezone.now())
    return user


def test_buy_sell_end_to_end_on_phone(client, campus):
    """M3 acceptance: post a Buy & Sell item through the 3-step wizard."""
    user = _approved_seller()
    client.force_login(user)
    category = f.ItemCategoryFactory()
    client.post(reverse("locations:choose"), {"campus": campus.pk})
    response = client.post(reverse("listings:post_start", args=["buy-sell"]))
    listing = Listing.objects.filter(owner=user, status="draft").latest("pk")
    assert response.url == reverse("listings:wizard", args=[listing.pk, 1])
    r = client.post(
        reverse("listings:photo_upload", args=[listing.pk]),
        {"photo": _jpeg()},
        HTTP_HX_REQUEST="true",
    )
    assert r.status_code == 200
    photo = listing.photos.get()
    from apps.core.images import has_exif

    photo.image.open()
    assert not has_exif(photo.image.read())
    client.post(reverse("listings:wizard", args=[listing.pk, 1]))
    r = client.post(
        reverse("listings:wizard", args=[listing.pk, 2]),
        {
            "title": "HP laptop 8GB RAM",
            "description": "Works well",
            "price": "1500",
            "price_period": "total",
            "lat": "7.0012345",
            "lng": "-1.0012345",
            "d-category": category.pk,
            "d-condition": "used",
        },
    )
    assert r.status_code == 302, r.content
    listing.refresh_from_db()
    assert (listing.lat, listing.lng) != (7.0012345, -1.0012345)  # snapped
    r = client.post(
        reverse("listings:wizard", args=[listing.pk, 3]),
        {
            "phone": "0241234567",
            "chat": "on",
            "contact_visibility": "public",
            "keep_campuses": [str(campus.pk)],
        },
    )
    assert r.status_code == 302, r.content
    listing.refresh_from_db()
    assert listing.status == "active" and listing.seller_type == "student"
    page = client.get(listing.get_absolute_url(), HTTP_USER_AGENT="Mozilla/5.0 (Android) Mobile")
    assert page.status_code == 200 and b"HP laptop 8GB RAM" in page.content


def test_new_seller_goes_to_review(campus):
    user = f.UserFactory()
    listing = services.create_draft(user, "buy-sell", LocationContext(campus=campus))
    listing.title = "Bluetooth speaker"
    listing.save()
    f.ItemDetailsFactory(listing=listing)
    services.publish(listing)
    assert listing.status == Listing.Status.PENDING_REVIEW


def test_phone_number_never_in_initial_html(client, campus):
    listing = f.ListingFactory(contact_visibility="public")
    f.ContactChannelFactory(card=listing.contact_card, kind="phone", value="+233241119999")
    f.ContactChannelFactory(card=listing.contact_card, kind="chat", value="")
    html = client.get(listing.get_absolute_url()).content.decode()
    assert "241119999" not in html and "Show number" in html
    reveal = client.post(reverse("contacts:tap", args=[listing.pk, "phone"]))
    assert "+233241119999" in reveal.content.decode()


def test_members_only_listing_hides_contacts_from_guests(client):
    listing = f.ListingFactory(contact_visibility="members")
    f.ContactChannelFactory(card=listing.contact_card, kind="whatsapp", value="+233241118888")
    html = client.get(listing.get_absolute_url()).content.decode()
    assert "Log in to contact this person" in html
    assert "241118888" not in html and "wa.me/233" not in html
    assert client.post(reverse("contacts:tap", args=[listing.pk, "whatsapp"])).status_code == 404


def test_whatsapp_tap_redirects_with_prefilled_text(client):
    listing = f.ListingFactory(title="Gas cylinder")
    f.ContactChannelFactory(card=listing.contact_card, kind="whatsapp", value="+233241118888")
    r = client.post(reverse("contacts:tap", args=[listing.pk, "whatsapp"]))
    assert r.url.startswith("https://wa.me/233241118888?text=") and "Gas%20cylinder" in r.url


def test_campus_autolink_radius():
    near = f.CampusFactory(lat=7.0, lng=-1.0)
    far = f.CampusFactory(lat=7.2, lng=-1.0)
    listing = f.ListingFactory(lat=7.01, lng=-1.0)
    services.autolink_campuses(listing)
    linked = set(listing.campus_links.values_list("campus_id", flat=True))
    assert near.pk in linked and far.pk not in linked
    link = ListingCampus.objects.get(listing=listing, campus=near)
    assert 1000 < link.distance_m < 1200


def test_manual_link_and_exclusion_survive_autolink():
    near = f.CampusFactory(lat=7.0, lng=-1.0)
    other = f.CampusFactory(lat=9.0, lng=-1.0)
    listing = f.ListingFactory(lat=7.0, lng=-1.0)
    services.autolink_campuses(listing)
    services.update_campus_links(listing, keep_ids=[], add_ids=[other.pk])
    services.autolink_campuses(listing)
    assert ListingCampus.objects.get(listing=listing, campus=near).is_excluded
    assert ListingCampus.objects.filter(listing=listing, campus=other, is_manual=True).exists()


def test_location_snapping():
    listing = f.ListingFactory()
    services.set_point(listing, 7.123456, -1.234567)
    assert listing.lat != 7.123456
    assert config.LOCATION_SNAP_M == 200


def test_ranking_formula():
    now = timezone.now()
    listing = f.ListingFactory(
        published_at=now - timedelta(days=7), taps_7d=2, likes_7d=1, views_7d=10, reports_count=1
    )
    expected = (
        1.0 * math.exp(-7 / 7)
        + 1.0 * min(math.log1p(3 * 2 + 2 * 1 + 0.2 * 10), 3.0)
        + 0.3 * (0 + 0)
        - 0.5 * 1
    )
    assert services.compute_score(
        listing, now, photo_count=0, owner_verified=False
    ) == pytest.approx(expected)
    assert services.compute_score(
        listing, now, photo_count=3, owner_verified=True
    ) == pytest.approx(expected + 0.6)


def test_lifecycle_transitions_time_travel():
    owner = f.UserFactory()
    listing = f.ListingFactory(owner=owner, published_at=timezone.now())
    booster = f.BoostFactory(listing=listing)
    start = timezone.now()
    with time_machine.travel(start + timedelta(days=14, hours=1)):
        services.run_lifecycle()
        listing.refresh_from_db()
        assert listing.status == "needs_check"
        assert owner.notifications.filter(trigger="still_available").exists()
    with time_machine.travel(start + timedelta(days=30, hours=1)):
        services.run_lifecycle()
        listing.refresh_from_db()
        assert listing.status == "expired"
        booster.refresh_from_db()
        assert booster.ends_at <= timezone.now()
    f.ListingPhotoFactory(listing=listing)
    with time_machine.travel(start + timedelta(days=90, hours=1)):
        services.run_lifecycle()
        listing.refresh_from_db()
        assert listing.status == "archived" and listing.photos.count() == 0
    # Idempotent: running again changes nothing.
    with time_machine.travel(start + timedelta(days=91)):
        assert services.run_lifecycle()["archived"] == 0


def test_section_expiry_override():
    config.SECTION_EXPIRY_OVERRIDES = {"rooms": {"expire": 45}}
    assert services.section_threshold("rooms", "expire") == 45
    assert services.section_threshold("buy-sell", "expire") == 30
    config.SECTION_EXPIRY_OVERRIDES = {}


def test_food_and_event_expire_on_their_own_dates():
    food = f.FoodDetailsFactory().listing
    event = f.EventDetailsFactory().listing
    for item in (food, event):
        item.expires_at = services.compute_expires_at(item)
        item.save()
    with time_machine.travel(timezone.now() + timedelta(hours=3)):
        services.run_lifecycle()
    food.refresh_from_db()
    event.refresh_from_db()
    assert food.status == "expired" and event.status == "active"


def test_one_tap_link_confirms_without_login(client):
    listing = f.ListingFactory(status="needs_check")
    url = reverse("listings:one_tap", args=[services.check_token(listing, "confirm")])
    assert client.get(url).status_code == 200
    listing.refresh_from_db()
    assert listing.status == "needs_check"  # GET never changes anything
    client.post(url)
    listing.refresh_from_db()
    assert listing.status == "active" and listing.confirmed_at


def test_one_tap_taken_ends_boost(client):
    listing = f.ListingFactory()
    boost = f.BoostFactory(listing=listing)
    client.post(reverse("listings:one_tap", args=[services.check_token(listing, "taken")]))
    listing.refresh_from_db()
    boost.refresh_from_db()
    assert listing.status == "taken" and boost.ends_at <= timezone.now()


def test_need_food_hidden_from_guests(client):
    details = f.FoodDetailsFactory(post_kind="need_food")
    listing = details.listing
    assert listing not in selectors.visible_listings(None)
    assert client.get(listing.get_absolute_url()).status_code == 404
    assert listing.effective_visibility == "members"


@pytest.mark.parametrize("slug", list(SECTIONS))
def test_every_section_page_and_detail_render(client, campus, slug):
    if slug == "trips":
        SectionAvailability.objects.create(section="trips", enabled=True)
    factory_name = {
        "rooms": "RoomDetailsFactory",
        "roommates": "RoommateDetailsFactory",
        "short-stays": "ShortStayDetailsFactory",
        "buy-sell": "ItemDetailsFactory",
        "wanted": "WantedDetailsFactory",
        "free-leaving": "ItemDetailsFactory",
        "services": "ServiceDetailsFactory",
        "jobs": "JobDetailsFactory",
        "job-requests": "JobRequestDetailsFactory",
        "errands": "ErrandDetailsFactory",
        "food": "FoodDetailsFactory",
        "events": "EventDetailsFactory",
        "notes": "NoteDetailsFactory",
        "study": "StudyDetailsFactory",
        "lost-found": "LostFoundDetailsFactory",
        "trips": "TripDetailsFactory",
        "alerts": "AlertDetailsFactory",
        "ask": "QuestionDetailsFactory",
    }[slug]
    details = getattr(f, factory_name)(listing__section=slug)
    listing = details.listing
    f.ListingCampusFactory(listing=listing, campus=campus)
    user = f.UserFactory()
    client.force_login(user)
    page = client.get(reverse("listings:section_campus", args=[campus.slug, slug]))
    assert page.status_code == 200
    assert listing.title.encode() in page.content
    assert client.get(listing.get_absolute_url()).status_code == 200
    assert listing.card_info is not None


def test_section_filters_apply(client, campus):
    a = f.RoomDetailsFactory(gender="female").listing
    b = f.RoomDetailsFactory(gender="male").listing
    for item in (a, b):
        f.ListingCampusFactory(listing=item, campus=campus)
    page = client.get(
        reverse("listings:section_campus", args=[campus.slug, "rooms"]), {"gender": "female"}
    )
    assert a.title.encode() in page.content and b.title.encode() not in page.content


def test_disabled_section_hidden_everywhere(client, campus):
    assert (
        client.get(reverse("listings:section_campus", args=[campus.slug, "trips"])).status_code
        == 404
    )
    SectionAvailability.objects.create(section="jobs", campus=campus, enabled=False)
    assert (
        client.get(reverse("listings:section_campus", args=[campus.slug, "jobs"])).status_code
        == 404
    )
    home = client.get(reverse("listings:campus_home", args=[campus.slug])).content.decode()
    assert f"/{campus.slug}/jobs/" not in home and f"/{campus.slug}/rooms/" in home
    client.force_login(f.UserFactory())
    client.post(reverse("locations:choose"), {"campus": campus.pk})
    picker = client.get(reverse("listings:post")).content.decode()
    assert "/post/new/jobs/" not in picker and "/post/new/trips/" not in picker


def test_sort_by_distance_from_point_and_campus(client, campus):
    near = f.ListingFactory(lat=7.001, lng=-1.0, title="Near thing")
    far = f.ListingFactory(lat=7.02, lng=-1.0, title="Far thing")
    for item in (near, far):
        f.ListingCampusFactory(listing=item, campus=campus)
    url = reverse("listings:section_campus", args=[campus.slug, "buy-sell"])
    html = client.get(url, {"sort": "distance", "lat": "7.021", "lng": "-1.0"}).content.decode()
    assert html.index("Far thing") < html.index("Near thing")
    html = client.get(url, {"sort": "distance"}).content.decode()  # falls back to the campus point
    assert html.index("Near thing") < html.index("Far thing")


def test_boosted_slots_capped_and_labelled(campus):
    items = [f.ListingFactory() for _ in range(6)]
    for item in items:
        f.BoostFactory(listing=item)
    qs = selectors.visible_listings(None)
    assert len(selectors.boosted_slots(qs)) == config.BOOST_SLOTS_PER_PAGE
    now = timezone.now()
    assert [x.pk for x in selectors.boosted_slots(qs, now=now)] == [
        x.pk for x in selectors.boosted_slots(qs, now=now)
    ]


def test_search_logs_event_with_result_count(client, campus):
    from apps.telemetry.models import Event
    from apps.telemetry.services import flush

    item = f.ListingFactory(title="Samsung Galaxy phone")
    f.ListingCampusFactory(listing=item, campus=campus)
    client.post(reverse("locations:choose"), {"campus": campus.pk})
    page = client.get(reverse("listings:search"), {"q": "galaxy"}, HTTP_USER_AGENT="Mozilla/5.0")
    assert b"Samsung Galaxy phone" in page.content
    client.get(reverse("listings:search"), {"q": "unicorn"}, HTTP_USER_AGENT="Mozilla/5.0")
    flush()
    events = {e.meta["query"]: e.meta["results"] for e in Event.objects.filter(kind="search")}
    assert events == {"galaxy": 1, "unicorn": 0}


def test_map_pages_have_attribution(client, campus):
    listing = f.ListingFactory()
    html = client.get(listing.get_absolute_url()).content.decode()
    assert "OpenStreetMap" in html and "data-attribution" in html
    html = client.get(reverse("listings:nearby") + "?lat=7&lng=-1").content.decode()
    assert "data-attribution" in html and 'data-rings="500,1000,2000"' in html


def test_service_worker_never_caches_tiles(client, db):
    js = client.get("/sw.js").content.decode()
    assets_line = next(line for line in js.splitlines() if line.startswith("const ASSETS"))
    assert "openstreetmap" not in assets_line and "{z}" not in js
    assert (
        "if (url.origin !== self.location.origin) return;" in js
    )  # cross-origin (tiles) never handled
