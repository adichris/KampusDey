"""Sitemaps: campuses, sections, active listings, hostels. External jobs are never included."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.hostels.models import Hostel
from apps.listings.models import Listing
from apps.locations.models import Campus
from apps.sitesettings.services import enabled_sections


class CampusSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Campus.objects.visible().order_by("pk")

    def lastmod(self, obj):
        return obj.updated_at


class SectionSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        out = []
        for campus in Campus.objects.visible().order_by("pk"):
            for section in enabled_sections(campus):
                out.append((campus.slug, section.slug))
        return out

    def location(self, item):
        return reverse("listings:section_campus", args=item)


class ListingSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.5
    limit = 5000

    def items(self):
        return (
            Listing.objects.filter(status__in=Listing.VISIBLE_STATUSES, is_hidden=False)
            .exclude(section="food")
            .order_by("-published_at")
        )

    def lastmod(self, obj):
        return obj.updated_at


class HostelSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Hostel.objects.order_by("pk")

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {"campuses": CampusSitemap, "sections": SectionSitemap, "listings": ListingSitemap, "hostels": HostelSitemap}
