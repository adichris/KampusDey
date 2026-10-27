import pytest
from django.contrib.contenttypes.models import ContentType

from apps.listings import services as listing_services
from apps.moderation.models import BannedTerm, ModerationItem
from apps.moderation.seed import seed_banned_terms
from apps.moderation.services import ModerationBlocked, check_listing, decide, suggest_price_ranges
from tests import factories as f

pytestmark = pytest.mark.django_db


def _draft(**kw):
    owner = kw.pop("owner", None) or f.UserFactory()
    f.ListingFactory.create_batch(3, owner=owner, section="services")
    listing = f.ListingFactory(
        owner=owner, status="draft", published_at=None, approved_at=None, **kw
    )
    f.ItemDetailsFactory(
        listing=listing, category=kw.pop("category", None) or f.ItemCategoryFactory()
    )
    return listing


def test_negative_price_rejected():
    listing = _draft(price=-5)
    with pytest.raises((ModerationBlocked, listing_services.ListingError)):
        listing_services.publish(listing)


def test_price_outside_category_range_goes_to_review():
    cat = f.ItemCategoryFactory(min_price=50, max_price=500)
    listing = _draft(price=5000)
    listing.itemdetails.category = cat
    listing.itemdetails.save()
    listing.__dict__.pop("details", None)
    verdict = check_listing(listing)
    assert verdict.review and not verdict.blocked


def test_duplicate_post_blocked():
    owner = f.UserFactory()
    f.ListingFactory(owner=owner, title="Neat HP laptop for sale cheap")
    listing = _draft(owner=owner, title="Neat HP laptop for sale cheap!")
    with pytest.raises(ModerationBlocked, match="similar post"):
        listing_services.publish(listing)


def test_near_duplicate_across_owners_goes_to_review():
    other = f.ListingFactory(title="Big blue mattress double size")
    listing = _draft(title="Big blue mattress double size", town=other.town)
    assert check_listing(listing).review


def test_banned_term_actions():
    seed_banned_terms()
    listing = _draft(title="Buying instagram followers cheap")
    assert check_listing(listing).review
    blocked = _draft(title="Counterfeit certificates available")
    assert check_listing(blocked).blocked
    BannedTerm.objects.create(term="totally banned", action="block", applies_to="listing")
    assert check_listing(_draft(title="this is totally banned stuff")).blocked


def test_banned_term_post_goes_to_review_queue():
    seed_banned_terms()
    listing = _draft(title="Get rich quick course")
    listing_services.publish(listing)
    listing.refresh_from_db()
    assert listing.status == "pending_review"
    assert ModerationItem.objects.filter(
        content_type=ContentType.objects.get_for_model(listing), object_id=listing.pk
    ).exists()


def test_moderation_decisions():
    listing = f.ListingFactory(status="pending_review", is_hidden=True)
    item = f.ModerationItemFactory(target=listing)
    decide(item, True)
    listing.refresh_from_db()
    assert listing.status == "active" and not listing.is_hidden
    other = f.ListingFactory(status="pending_review")
    decide(f.ModerationItemFactory(target=other), False)
    other.refresh_from_db()
    assert other.status == "archived" and other.is_hidden


def test_duplicate_photo_by_same_owner_blocked():
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    owner = f.UserFactory()
    first = f.ListingFactory(owner=owner)
    second = f.ListingFactory(owner=owner, status="draft")

    def upload():
        img = Image.new("RGB", (64, 64))
        for x in range(64):
            for y in range(64):
                img.putpixel((x, y), (x * 4, y * 4, 0))
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        return SimpleUploadedFile("a.jpg", buf.getvalue(), content_type="image/jpeg")

    listing_services.add_photo(first, upload())
    with pytest.raises(listing_services.ListingError, match="already posted"):
        listing_services.add_photo(second, upload())


def test_price_range_suggestions_need_30_samples():
    cat = f.ItemCategoryFactory()
    for price in range(1, 31):
        f.ItemDetailsFactory(category=cat, listing=f.ListingFactory(price=price * 10))
    assert suggest_price_ranges() == 1
    from apps.moderation.models import PriceRangeSuggestion

    s = PriceRangeSuggestion.objects.get()
    assert s.samples == 30 and s.suggested_min == 20 and s.suggested_max == 280
    cat.refresh_from_db()
    assert cat.min_price is None  # never applied automatically


def test_scam_alert_board_shows_only_published(client):
    from django.utils import timezone

    f.ScamAlertFactory(
        name="Shown Scammer", is_published=True, confirmed_at=timezone.now(), evidence_note="SECRET"
    )
    f.ScamAlertFactory(name="Unconfirmed Person")
    html = client.get("/scam-alerts/").content.decode()
    assert "Shown Scammer" in html and "Unconfirmed Person" not in html and "SECRET" not in html


def test_csp_header_on_key_pages(client):
    response = client.get("/")
    csp = response["Content-Security-Policy"]
    assert (
        "script-src 'self' 'nonce-" in csp
        and "unsafe-inline" not in csp
        and "unsafe-eval" not in csp
    )
    html = response.content.decode()
    import re

    for tag in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html):
        assert "nonce=" in tag or "application/ld+json" in tag
    assert ' style="' not in html
