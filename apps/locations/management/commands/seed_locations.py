"""Seed Ghana's 16 regions and the Appendix A starter campuses (names only, points null)."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.locations.models import Campus, Institution, Region, ReviewStatus, Source, Town

FIXTURES = Path(settings.BASE_DIR) / "fixtures"


class Command(BaseCommand):
    help = "Seed regions and starter campuses (idempotent; never adds coordinates)."

    @transaction.atomic
    def handle(self, *args, **options):
        for row in json.loads((FIXTURES / "regions.json").read_text(encoding="utf-8")):
            Region.objects.update_or_create(
                slug=slugify(row["name"]),
                defaults={"name": row["name"]},
                create_defaults={"name": row["name"], "review_status": ReviewStatus.VERIFIED},
            )
        for row in json.loads((FIXTURES / "campuses_seed.json").read_text(encoding="utf-8")):
            region = Region.objects.get(slug=slugify(row["region"]))
            town = Town.objects.filter(region=region, name__iexact=row["town"]).first()
            if town is None:
                town = Town.objects.create(
                    slug=slugify(f"{row['town']}-{region.name}"), name=row["town"], region=region
                )
            inst = Institution.objects.filter(name__iexact=row["name"]).first()
            if inst is None:
                inst = Institution.objects.create(
                    slug=slugify(row["name"]), name=row["name"], short_name=row["short_name"],
                    kind=row["kind"], confidence=0.8,
                )
            slug = slugify(row["short_name"] or row["name"])
            campus = Campus.objects.filter(slug=slug).first() or Campus.objects.filter(institution=inst).first()
            if campus is None:
                Campus.objects.create(
                    slug=slug, institution=inst, name=row["name"], short_name=row["short_name"],
                    kind=row["kind"], town=town, confidence=0.8,
                )
        from apps.external.seed import seed_sources
        from apps.listings.seed import seed_categories
        from apps.moderation.seed import seed_banned_terms

        seed_categories()
        seed_banned_terms()
        seed_sources()
        self.stdout.write(
            self.style.SUCCESS(
                f"Regions: {Region.objects.count()}, towns: {Town.objects.count()}, "
                f"campuses: {Campus.objects.count()}"
            )
        )
