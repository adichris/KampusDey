import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(name="locations.update_geolite2")
def update_geolite2():
    from .geoip import update_geolite2 as run

    try:
        return str(run())
    except RuntimeError as exc:
        logger.info("GeoLite2 update skipped: %s", exc)
        return None


@shared_task(name="locations.quarterly_refresh")
def quarterly_refresh():
    """Quarterly: Wikidata, OSM campuses and areas, then report and notify superadmins."""
    from apps.accounts.models import User
    from apps.notifications.services import notify

    from .models import Campus, ReviewStatus

    before = Campus.objects.filter(review_status=ReviewStatus.UNVERIFIED).count()
    for command in ("import_wikidata_institutions", "import_osm_campuses", "import_osm_areas"):
        try:
            call_command(command)
        except Exception:
            logger.exception("%s failed", command)
    call_command("locations_report")
    new = Campus.objects.filter(review_status=ReviewStatus.UNVERIFIED).count() - before
    if new > 0:
        for admin in User.objects.filter(is_superuser=True, is_active=True):
            notify(admin, "campus_request", f"{new} new unverified campuses to review", url="/admin/")
    return new
