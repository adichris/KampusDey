"""Unfold dashboard callback: KPIs, charts by campus/region/section, search gaps, queues (§6.12)."""

import json
from collections import Counter
from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import gettext as _


def _period_counts(model, field, days):
    since = timezone.now() - timedelta(days=days)
    return model.objects.filter(**{f"{field}__gte": since}).count()


def dashboard_callback(request, context):
    from apps.accounts.models import User, VerificationRequest
    from apps.engagement.models import Report
    from apps.external.models import ExternalJob, ExternalSource, Place, PlaceClaim
    from apps.listings.models import Listing
    from apps.listings.sections import SECTIONS
    from apps.locations.models import Area, Campus, CampusRequest, Institution
    from apps.moderation.models import ModerationItem
    from apps.telemetry.models import DailyCampusStats, Event
    from apps.telemetry.services import flush

    flush()
    kpis = []
    for label, days in ((_("Today"), 1), (_("7 days"), 7), (_("30 days"), 30)):
        since = timezone.now() - timedelta(days=days)
        events = Counter(Event.objects.filter(created_at__gte=since).values_list("kind", flat=True))
        kpis.append(
            {
                "label": label,
                "signups": _period_counts(User, "date_joined", days),
                "posts": Listing.objects.filter(published_at__gte=since).count(),
                "views": events.get("view", 0),
                "taps": events.get("tap", 0),
            }
        )
    since30 = timezone.now() - timedelta(days=30)
    by_campus = list(
        DailyCampusStats.objects.filter(date__gte=since30.date())
        .values("campus__short_name", "campus__name")
        .annotate(views=Sum("views"), taps=Sum("taps"), posts=Sum("posts"))
        .order_by("-views")[:12]
    )
    by_region = list(
        Listing.objects.filter(status__in=Listing.VISIBLE_STATUSES)
        .values("town__region__name")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    by_section = {
        str(SECTIONS[row["section"]].label): row["n"]
        for row in Listing.objects.filter(status__in=Listing.VISIBLE_STATUSES).values("section").annotate(n=Count("id"))
        if row["section"] in SECTIONS
    }
    searches = Counter()
    zero = Counter()
    for meta in Event.objects.filter(kind="search", created_at__gte=since30).values_list("meta", flat=True)[:20000]:
        q = (meta or {}).get("query", "").strip().lower()
        if not q:
            continue
        searches[q] += 1
        if not (meta or {}).get("results"):
            zero[q] += 1
    context.update(
        {
            "kpis": kpis,
            "active_listings": Listing.objects.filter(status__in=Listing.VISIBLE_STATUSES, is_hidden=False).count(),
            "chart_campus": json.dumps(
                {
                    "labels": [r["campus__short_name"] or r["campus__name"] for r in by_campus],
                    "datasets": [
                        {"label": str(_("Views")), "data": [r["views"] or 0 for r in by_campus]},
                        {"label": str(_("Taps")), "data": [r["taps"] or 0 for r in by_campus]},
                    ],
                }
            ),
            "chart_region": json.dumps(
                {"labels": [r["town__region__name"] for r in by_region],
                 "datasets": [{"label": str(_("Active listings")), "data": [r["n"] for r in by_region]}]}
            ),
            "chart_section": json.dumps(
                {"labels": list(by_section), "datasets": [{"label": str(_("Active listings")), "data": list(by_section.values())}]}
            ),
            "top_searches": searches.most_common(15),
            "zero_searches": zero.most_common(15),
            "queues": [
                (_("Moderation"), ModerationItem.objects.filter(status="pending").count(), "admin:moderation_moderationitem_changelist"),
                (_("Reports"), Report.objects.filter(status="open").count(), "admin:engagement_report_changelist"),
                (_("Verification requests"), VerificationRequest.objects.filter(status="pending").count(), "admin:accounts_verificationrequest_changelist"),
                (_("Campus requests"), CampusRequest.objects.filter(status="pending").count(), "admin:locations_campusrequest_changelist"),
                (_("Place claims"), PlaceClaim.objects.filter(status="pending").count(), "admin:external_placeclaim_changelist"),
            ],
            "location_tiles": [
                (_("Unverified campuses"), Campus.objects.filter(review_status="unverified").count()),
                (_("Campuses without points"), Campus.objects.filter(lat__isnull=True).count()),
                (_("Unverified areas"), Area.objects.filter(review_status="unverified").count()),
                (_("Flagged institutions"), Institution.objects.filter(gtec_status__in=["expired", "unaccredited"]).count()),
            ],
            "external_tiles": [
                (_("Places"), Place.objects.visible().count()),
                (_("Unclaimed / claimed"), f"{Place.objects.filter(status='unclaimed').count()} / {Place.objects.filter(status='claimed').count()}"),
                (_("Pending claims"), PlaceClaim.objects.filter(status="pending").count()),
                (_("Active remote jobs"), ExternalJob.objects.visible().count()),
            ],
            "sources": ExternalSource.objects.all(),
        }
    )
    return context


def _badge(count):
    return str(count) if count else None


def badge_moderation(request):
    from apps.moderation.models import ModerationItem

    return _badge(ModerationItem.objects.filter(status="pending").count())


def badge_reports(request):
    from apps.engagement.models import Report

    return _badge(Report.objects.filter(status="open").count())


def badge_verifications(request):
    from apps.accounts.models import VerificationRequest

    return _badge(VerificationRequest.objects.filter(status="pending").count())


def badge_campus_requests(request):
    from apps.locations.models import CampusRequest

    return _badge(CampusRequest.objects.filter(status="pending").count())


def badge_unverified_campuses(request):
    from apps.locations.models import Campus

    return _badge(Campus.objects.filter(review_status="unverified").count())


def badge_claims(request):
    from apps.external.models import PlaceClaim

    return _badge(PlaceClaim.objects.filter(status="pending").count())
