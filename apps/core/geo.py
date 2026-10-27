"""Small, dependency-free geo helpers.

Points are (lat, lng) WGS84 floats. Distances use the haversine formula on a spherical earth,
which is accurate to well under 0.5% at campus scale. Database queries pre-filter with a
bounding box (index friendly) and then annotate an exact distance with SQL math functions that
both PostgreSQL and SQLite support through Django.
"""

from __future__ import annotations

import math

from django.db.models import F, FloatField, Value
from django.db.models.functions import ACos, Cos, Greatest, Least, Radians, Sin

EARTH_RADIUS_M = 6_371_008.8
M_PER_DEG_LAT = 111_320.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bbox(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lng, max_lng) enclosing a circle of radius_m."""
    dlat = radius_m / M_PER_DEG_LAT
    dlng = radius_m / (M_PER_DEG_LAT * max(math.cos(math.radians(lat)), 1e-6))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def snap(lat: float, lng: float, grid_m: int) -> tuple[float, float]:
    """Snap a point to a ~grid_m metre grid so exact homes are never stored."""
    if not grid_m or grid_m <= 0:
        return lat, lng
    step_lat = grid_m / M_PER_DEG_LAT
    snapped_lat = round(lat / step_lat) * step_lat
    step_lng = grid_m / (M_PER_DEG_LAT * max(math.cos(math.radians(snapped_lat)), 1e-6))
    snapped_lng = round(lng / step_lng) * step_lng
    return round(snapped_lat, 6), round(snapped_lng, 6)


def walking_minutes(distance_m: float | None, m_per_min: int) -> int | None:
    if distance_m is None:
        return None
    return max(1, math.ceil(distance_m / max(m_per_min, 1)))


def within_radius(qs, lat: float, lng: float, radius_m: float, lat_field="lat", lng_field="lng"):
    min_lat, max_lat, min_lng, max_lng = bbox(lat, lng, radius_m)
    return qs.filter(
        **{
            f"{lat_field}__gte": min_lat,
            f"{lat_field}__lte": max_lat,
            f"{lng_field}__gte": min_lng,
            f"{lng_field}__lte": max_lng,
        }
    )


def distance_expression(lat: float, lng: float, lat_field="lat", lng_field="lng"):
    """Spherical law of cosines distance in metres as a DB expression."""
    lat_r = math.radians(lat)
    inner = Value(math.sin(lat_r)) * Sin(Radians(F(lat_field))) + Value(math.cos(lat_r)) * Cos(
        Radians(F(lat_field))
    ) * Cos(Radians(F(lng_field)) - Value(math.radians(lng)))
    clamped = Least(Greatest(inner, Value(-1.0)), Value(1.0))
    return ACos(clamped, output_field=FloatField()) * Value(EARTH_RADIUS_M)


def annotate_distance(
    qs, lat: float, lng: float, lat_field="lat", lng_field="lng", name="distance_m"
):
    return qs.annotate(**{name: distance_expression(lat, lng, lat_field, lng_field)})


def nearby(qs, lat, lng, radius_m, lat_field="lat", lng_field="lng", name="distance_m"):
    qs = within_radius(qs, lat, lng, radius_m, lat_field, lng_field)
    qs = annotate_distance(qs, lat, lng, lat_field, lng_field, name)
    return qs.filter(**{f"{name}__lte": radius_m})


# ---------------------------------------------------------------------------
# GeoJSON helpers (region/district boundaries)
# ---------------------------------------------------------------------------
def _ring_contains(ring, x, y) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def polygon_contains(polygon, lng: float, lat: float) -> bool:
    """GeoJSON Polygon coordinates: [outer_ring, hole1, ...]."""
    if not polygon or not _ring_contains(polygon[0], lng, lat):
        return False
    return not any(_ring_contains(hole, lng, lat) for hole in polygon[1:])


def geometry_contains(geometry: dict | None, lat: float, lng: float) -> bool:
    if not geometry:
        return False
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return polygon_contains(coords, lng, lat)
    if kind == "MultiPolygon":
        return any(polygon_contains(poly, lng, lat) for poly in coords)
    return False


def to_multipolygon(geometry: dict | None) -> dict | None:
    if not geometry:
        return None
    if geometry.get("type") == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [geometry["coordinates"]]}
    if geometry.get("type") == "MultiPolygon":
        return geometry
    return None


def geometry_bbox(geometry: dict | None):
    """(min_lat, max_lat, min_lng, max_lng) of a (Multi)Polygon, or None."""
    if not geometry:
        return None
    xs, ys = [], []
    polys = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    for poly in polys:
        for ring in poly:
            for x, y, *_ in ring:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(ys), max(ys), min(xs), max(xs)


def parse_wkt_point(wkt: str | None) -> tuple[float, float] | None:
    """Parse Wikidata's `Point(lon lat)` into (lat, lng)."""
    if not wkt:
        return None
    text = wkt.strip()
    if "(" not in text:
        return None
    body = text[text.index("(") + 1 : text.rindex(")")].split()
    if len(body) < 2:
        return None
    lng, lat = float(body[0]), float(body[1])
    return lat, lng
