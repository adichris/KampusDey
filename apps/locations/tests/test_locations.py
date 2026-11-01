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
    client.post(
        reverse("locations:request"),
        {
            "name": "New Nursing Training College",
            "town_name": "Newtown",
            "region": region.pk,
            "email": "a@example.test",
        },
    )
    req = CampusRequest.objects.get()
    campus = approve_campus_request(req)
    assert (
        campus.kind == "nursing_midwifery" and campus.town.name == "Newtown" and campus.lat is None
    )
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


def _fake_maxmind(status=200):
    import io
    import tarfile
    from unittest import mock

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"fake-mmdb"
        info = tarfile.TarInfo("GeoLite2-City_20261028/GeoLite2-City.mmdb")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    resp = mock.MagicMock(status_code=status)
    resp.iter_content.return_value = [buf.getvalue()]
    resp.__enter__.return_value = resp
    return mock.patch("apps.locations.geoip.requests.get", return_value=resp)


def test_update_geolite2_streams_and_swaps_in(settings, tmp_path, db):
    from apps.locations.geoip import update_geolite2
    from apps.sitesettings.models import IntegrationSettings

    settings.GEOIP_PATH = str(tmp_path)
    integ = IntegrationSettings.load()
    integ.geolite2_account_id, integ.geolite2_license_key = "123", "key"
    integ.save()
    with _fake_maxmind() as get:
        path = update_geolite2()
    assert path.read_bytes() == b"fake-mmdb"
    assert get.call_args.kwargs["auth"] == ("123", "key") and get.call_args.kwargs["stream"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["GeoLite2-City.mmdb"]
    assert IntegrationSettings.load().geolite2_last_updated
    with _fake_maxmind(status=401), pytest.raises(RuntimeError, match="401"):
        update_geolite2()
    assert path.read_bytes() == b"fake-mmdb"  # a failed download keeps the old database
