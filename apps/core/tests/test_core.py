import io

import pytest
from PIL import Image

from apps.core import geo
from apps.core.images import clean_image, has_exif, hamming
from apps.core.templatetags.kd import ghs
from apps.core.text import mask_contacts, normalise_name, trigram_similarity
from apps.core.utils import is_bot, session_hash


def test_ghs_filter():
    assert ghs(1200) == "GH₵ 1,200"
    assert ghs("15.5") == "GH₵ 15.50"
    assert ghs(None) == ""


def test_haversine_and_walking():
    d = geo.haversine_m(7.0, -1.0, 7.0, -0.99)
    assert 1090 < d < 1110
    assert geo.walking_minutes(161, 80) == 3
    assert geo.walking_minutes(None, 80) is None


def test_snap_moves_point_onto_grid_and_is_stable():
    lat, lng = geo.snap(7.123456, -1.987654, 200)
    assert geo.haversine_m(7.123456, -1.987654, lat, lng) < 200
    assert geo.snap(lat, lng, 200) == (lat, lng)


def test_point_in_polygon_with_hole():
    poly = {"type": "Polygon", "coordinates": [
        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]]}
    assert geo.geometry_contains(poly, 2, 2)
    assert not geo.geometry_contains(poly, 5, 5)
    assert not geo.geometry_contains(poly, 20, 2)


def test_parse_wkt_point_order():
    assert geo.parse_wkt_point("Point(-2.3 7.3)") == (7.3, -2.3)


@pytest.mark.django_db
def test_distance_expression_matches_python():
    from tests.factories import CampusFactory

    campus = CampusFactory(lat=7.0, lng=-1.0)
    qs = geo.annotate_distance(type(campus).objects.filter(pk=campus.pk), 7.0, -0.99)
    assert abs(qs.get().distance_m - geo.haversine_m(7.0, -1.0, 7.0, -0.99)) < 2


def test_normalise_name():
    assert normalise_name("Univ. of Energy & Natural Resources") == "university of energy and natural resources"
    assert normalise_name("NMTC, Sunyani") == "nurses and midwifery training college sunyani"
    assert normalise_name("Sunyani Tech. Univ") == "sunyani technical university"


def test_trigram_similarity():
    assert trigram_similarity("Fresh iPhone 12 for sale", "Fresh iPhone 12 for sale!") == 1.0
    assert trigram_similarity("mattress", "laptop") < 0.2


@pytest.mark.parametrize(
    "text",
    [
        "call me 024 123 4567",
        "call 0241234567 now",
        "whatsapp +233 24 123 4567",
        "number 024-123-4567",
        "mail me at kofi@example.com",
        "see www.example.com/deal",
        "https://scam.example/xyz",
    ],
)
def test_mask_contacts(text):
    masked = mask_contacts(text)
    assert "[hidden]" in masked
    for leak in ("4567", "kofi@", "example.com", "scam.example"):
        assert leak not in masked


def test_mask_keeps_normal_text():
    assert mask_contacts("Is the room still available? Price 1200 ok") == "Is the room still available? Price 1200 ok"


def _jpeg_with_gps():
    img = Image.new("RGB", (50, 40), "red")
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    exif[0x8825] = {2: (5, 33, 0)}
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_clean_image_strips_exif():
    data = _jpeg_with_gps()
    assert has_exif(data)

    class Upload(io.BytesIO):
        size = len(data)
        name = "x.jpg"

    content, w, h, phash = clean_image(Upload(data), 8)
    assert (w, h) == (50, 40)
    assert not has_exif(content.read())
    assert len(phash) == 16


def test_clean_image_rejects_non_images():
    from django.core.exceptions import ValidationError

    class Upload(io.BytesIO):
        size = 10
        name = "x.jpg"

    with pytest.raises(ValidationError):
        clean_image(Upload(b"not an image at all"), 8)


def test_hamming():
    assert hamming("ffff", "ffff") == 0
    assert hamming("0", "f") == 4


def test_session_hash_has_no_raw_key_and_rotates_daily():
    from datetime import date

    a = session_hash("abc", date(2026, 1, 1))
    b = session_hash("abc", date(2026, 1, 2))
    assert a != b and "abc" not in a and len(a) == 64


def test_is_bot():
    assert is_bot("Googlebot/2.1")
    assert is_bot("")
    assert not is_bot("Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile")
