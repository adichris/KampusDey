import json
import re

import pytest
from django.core import mail
from django.urls import reverse

from apps.growth import services
from apps.growth.models import Referral
from tests import factories as f

pytestmark = pytest.mark.django_db


def _jsonld(html):
    blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    return [json.loads(b) for b in blocks]


def test_jobposting_structured_data_validates(client):
    job = f.JobDetailsFactory(job_type="internship").listing
    data = _jsonld(client.get(job.get_absolute_url()).content.decode())[0]
    assert data["@type"] == "JobPosting"
    for key in ("title", "description", "datePosted", "hiringOrganization", "jobLocation", "employmentType"):
        assert data[key]
    assert data["employmentType"] == "INTERN" and data["jobLocation"]["address"]["addressCountry"] == "GH"


def test_event_structured_data_validates(client):
    event = f.EventDetailsFactory().listing
    data = _jsonld(client.get(event.get_absolute_url()).content.decode())[0]
    assert data["@type"] == "Event" and data["startDate"] and data["location"]["name"] == "Great Hall"


def test_share_preview_has_title_price_photo(client):
    listing = f.ListingFactory(title="Study desk", price=250)
    f.ListingPhotoFactory(listing=listing)
    html = client.get(listing.get_absolute_url()).content.decode()
    assert 'property="og:title" content="Study desk — GH₵ 250"' in html
    assert 'property="og:image"' in html and "summary_large_image" in html


def test_sitemap_and_robots(client, campus):
    listing = f.ListingFactory()
    f.ListingCampusFactory(listing=listing, campus=campus)
    sitemap = client.get("/sitemap.xml").content.decode()
    assert listing.get_absolute_url() in sitemap and f"/{campus.slug}/rooms/" in sitemap
    assert "Sitemap:" in client.get("/robots.txt").content.decode()


def test_referral_rewarded_after_verified_email_and_first_post(client):
    ambassador = f.UserFactory()
    ambassador.profile.is_ambassador = True
    ambassador.profile.save()
    code = services.ensure_referral_code(ambassador.profile)
    client.get(reverse("referral", args=[code]))
    client.post(reverse("account_signup"), {"email": "ref@example.test", "password1": "Long-pass-9876", "password2": "Long-pass-9876"})
    referral = Referral.objects.get()
    new_user = referral.referred_user
    assert not services.maybe_reward_referral(new_user)  # email not verified, no post
    from allauth.account.models import EmailAddress

    EmailAddress.objects.filter(user=new_user).update(verified=True)
    f.ListingFactory(owner=new_user)
    assert services.maybe_reward_referral(new_user)
    ambassador.profile.refresh_from_db()
    assert ambassador.profile.bonus_boosts == 2
    assert not services.maybe_reward_referral(new_user)  # only once


def test_rent_check_needs_five_samples(client, campus):
    for price in (1000, 1200, 1400, 1600):
        listing = f.RoomDetailsFactory(listing__price=price, listing__price_period="per_year").listing
        f.ListingCampusFactory(listing=listing, campus=campus)
    rows = services.rent_check(campus)["rows"]
    assert rows and not rows[0]["enough"]
    listing = f.RoomDetailsFactory(listing__price=1800, listing__price_period="per_year").listing
    f.ListingCampusFactory(listing=listing, campus=campus)
    row = services.rent_check(campus)["rows"][0]
    assert row["enough"] and row["median"] == 1400 and row["low"] == 1000
    assert client.get(reverse("rent_check", args=[campus.slug])).status_code == 200


def test_weekly_digest_respects_opt_out(campus):
    user = f.UserFactory()
    user.profile.home_campus = campus
    user.profile.save()
    listing = f.ListingFactory()
    f.ListingCampusFactory(listing=listing, campus=campus)
    assert services.send_weekly_digest() == 1 and listing.title in mail.outbox[0].body
    user.notification_prefs.weekly_digest = False
    user.notification_prefs.save()
    assert services.send_weekly_digest() == 0


def test_spotlight_on_home(client, campus):
    spot = f.SpotlightFactory(campus=campus, blurb="Student Business of the Week")
    html = client.get(reverse("listings:campus_home", args=[campus.slug])).content.decode()
    assert "Student Business of the Week" in html and spot.listing.title in html
