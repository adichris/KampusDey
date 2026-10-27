import pytest
from django.urls import reverse

from apps.locations.models import CampusRequest
from apps.locations.services import approve_campus_request, nearest_campuses
from tests import factories as f

pytestmark = pytest.mark.django_db


def test_guest_choice_persists_in_signed_cookie(client, campus):
    client.post(reverse("locations:choose"), {"campus": campus.pk})
    assert campus.label in client.get("/").content.decode()
    client.cookies["kd_loc"] = "c:999"  # tampered cookie is ignored
    assert "Choose location" in client.get("/").content.decode()


def test_user_choice_saved_on_profile(client_user, user, campus):
    client_user.post(reverse("locations:choose"), {"campus": campus.pk})
    user.profile.refresh_from_db()
    assert user.profile.home_campus == campus and campus in user.profile.followed_campuses.all()


def test_other_town_choice(client, db):
    town = f.TownFactory()
    client.post(reverse("locations:choose"), {"town": town.pk})
    assert town.name in client.get("/").content.decode()


def test_nearest_campus_suggestion():
    near = f.CampusFactory(lat=7.0, lng=-1.0)
    far = f.CampusFactory(lat=8.0, lng=-1.0)
    f.CampusFactory(lat=None, lng=None)
    result = nearest_campuses(7.01, -1.0)
    assert result[0] == near and result[1] == far and len(result) == 2


def test_missing_geolite_db_causes_no_errors(client, db):
    assert client.get(reverse("locations:picker")).status_code == 200


def test_campus_request_flow(client, db):
    region = f.RegionFactory()
    client.post(reverse("locations:request"), {"name": "New Nursing Training College", "town_name": "Newtown",
                                               "region": region.pk, "email": "a@example.test"})
    req = CampusRequest.objects.get()
    campus = approve_campus_request(req)
    assert campus.kind == "nursing_midwifery" and campus.town.name == "Newtown" and campus.lat is None
    assert req.status == "added"


def test_unverified_campus_visible_rejected_hidden():
    a = f.CampusFactory(review_status="unverified")
    b = f.CampusFactory(review_status="rejected")
    visible = set(type(a).objects.visible())
    assert a in visible and b not in visible


def test_follow_toggle(client_user, user, campus):
    client_user.post(reverse("locations:follow", args=[campus.pk]))
    assert campus in user.profile.followed_campuses.all()
    client_user.post(reverse("locations:follow", args=[campus.pk]))
    assert campus not in user.profile.followed_campuses.all()
