from datetime import timedelta

import pytest
import time_machine
from django.urls import reverse
from django.utils import timezone

from apps.boosts.models import Boost
from apps.boosts.services import BoostRefused, boost, boosts_left, can_boost
from apps.listings.services import mark_taken
from tests.factories import ListingFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_third_boost_in_seven_days_refused():
    user = UserFactory()
    listings = ListingFactory.create_batch(3, owner=user)
    boost(user, listings[0])
    boost(user, listings[1])
    with pytest.raises(BoostRefused, match="used your 2 free boosts"):
        boost(user, listings[2])
    assert boosts_left(user) == 0
    with time_machine.travel(timezone.now() + timedelta(days=7, minutes=1)):
        assert can_boost(user, listings[2])


def test_boost_needs_account_age_and_active_listing():
    young = UserFactory(date_joined=timezone.now() - timedelta(hours=1))
    assert not can_boost(young, ListingFactory(owner=young))
    user = UserFactory()
    assert not can_boost(user, ListingFactory(owner=user, status="expired"))
    assert not can_boost(user, ListingFactory())  # someone else's


def test_no_double_boost_and_source_is_free():
    user = UserFactory()
    listing = ListingFactory(owner=user)
    item = boost(user, listing)
    assert item.source == Boost.Source.FREE
    assert not can_boost(user, listing)


def test_boost_ends_when_listing_taken():
    user = UserFactory()
    listing = ListingFactory(owner=user)
    item = boost(user, listing)
    mark_taken(listing)
    item.refresh_from_db()
    assert not item.is_active


def test_ambassador_bonus_boosts_extend_limit():
    user = UserFactory()
    user.profile.bonus_boosts = 1
    user.profile.save()
    listings = ListingFactory.create_batch(3, owner=user)
    for item in listings:
        boost(user, item)
    user.profile.refresh_from_db()
    assert user.profile.bonus_boosts == 0


def test_dashboard_boost_message(client):
    user = UserFactory()
    client.force_login(user)
    listings = ListingFactory.create_batch(3, owner=user)
    for item in listings:
        client.post(reverse("dashboard:boost", args=[item.pk]))
    page = client.get(reverse("dashboard:home"))
    assert page.status_code == 200
    assert Boost.objects.filter(user=user).count() == 2
