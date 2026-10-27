"""Seed the two sources as pending_review (DATA_SOURCES §14). An admin approves them."""

from .models import ExternalSource

SOURCES = [
    {
        "slug": "osm-places",
        "name": "OpenStreetMap places",
        "kind": ExternalSource.Kind.OSM_PLACES,
        "base_url": "https://overpass-api.de/api/interpreter",
        "terms_url": "https://www.openstreetmap.org/copyright",
        "licence": "ODbL 1.0",
        "attribution_text": "© OpenStreetMap contributors",
        "min_interval_minutes": 60 * 24,
    },
    {
        "slug": "remotive",
        "name": "Remotive remote jobs",
        "kind": ExternalSource.Kind.REMOTIVE_JOBS,
        "base_url": "https://remotive.com/api/remote-jobs",
        "terms_url": "https://github.com/remotive-com/remote-jobs-api",
        "licence": "Remotive public API terms",
        "attribution_text": "Remote jobs provided by Remotive",
        "min_interval_minutes": 360,
    },
]


def seed_sources():
    for row in SOURCES:
        ExternalSource.objects.get_or_create(slug=row["slug"], defaults=row)
