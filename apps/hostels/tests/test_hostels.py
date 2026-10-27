import pytest
from django.urls import reverse

from apps.hostels import services
from apps.listings import selectors
from tests import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def landlord():
    user = f.UserFactory()
    user.profile.role = "landlord"
    user.profile.save()
    return user


def test_zero_availability_hides_listing_and_restores(landlord, campus):
    hostel = f.HostelFactory(owner=landlord)
    hostel.campuses.add(campus)
    rt = f.HostelRoomTypeFactory(hostel=hostel, total_rooms=2, available_rooms=1)
    listing = services.sync_room_type_listing(rt)
    assert listing in selectors.for_campus(selectors.visible_listings(None), campus)
    services.step_available(rt, -1)
    listing.refresh_from_db()
    assert listing.status == "taken"
    assert listing not in selectors.search("", None, None, {"rooms"})[0]
    services.step_available(rt, +1)
    listing.refresh_from_db()
    assert listing.status == "active"


def test_stepper_clamps(landlord):
    rt = f.HostelRoomTypeFactory(hostel=f.HostelFactory(owner=landlord), total_rooms=3, available_rooms=3)
    services.sync_room_type_listing(rt)
    services.step_available(rt, +1)
    assert rt.available_rooms == 3
    services.set_available(rt, -4)
    assert rt.available_rooms == 0


def test_manager_views(client, landlord, campus):
    client.force_login(landlord)
    assert client.get(reverse("hostels:manager")).status_code == 200
    r = client.post(reverse("hostels:create"), {"name": "Green Lodge", "description": "Quiet", "rules": "",
                                                "town": campus.town_id, "campuses": [campus.pk], "amenities": ["wifi"]})
    hostel = landlord.hostels.get()
    assert r.status_code == 302
    client.post(reverse("hostels:room_type_new", args=[hostel.pk]),
                {"name": "Single", "room_type": "single", "gender": "mixed", "price": "4000", "price_period": "per_year",
                 "total_rooms": "4", "available_rooms": "1"})
    rt = hostel.room_types.get()
    assert rt.listing.section == "rooms" and rt.listing.roomdetails.wifi
    r = client.post(reverse("hostels:step", args=[hostel.pk, rt.pk, "down"]))
    assert b"0 / 4" in r.content
    for name in ("hostels:manage", "hostels:inquiries", "hostels:edit"):
        assert client.get(reverse(name, args=[hostel.pk])).status_code == 200
    assert client.get(hostel.get_absolute_url()).status_code == 200


def test_students_cannot_manage(client_user):
    assert b"landlords and agents" in client_user.get(reverse("hostels:manager")).content


def test_occupancy():
    hostel = f.HostelFactory()
    f.HostelRoomTypeFactory(hostel=hostel, total_rooms=4, available_rooms=1)
    f.HostelRoomTypeFactory(hostel=hostel, total_rooms=6, available_rooms=4)
    assert services.occupancy(hostel) == {"total": 10, "available": 5, "occupied": 5, "pct": 50}
