from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class GeoPointMixin(models.Model):
    """A WGS84 point stored as two floats.

    The build prompt specifies PostGIS; this project runs without GDAL/PostGIS on local
    machines, so points are stored as latitude/longitude and distances are computed with the
    haversine formula (see `apps.core.geo`). Recorded in docs/PROGRESS.md.
    """

    lat = models.FloatField(_("latitude"), null=True, blank=True)
    lng = models.FloatField(_("longitude"), null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def has_point(self) -> bool:
        return self.lat is not None and self.lng is not None

    @property
    def point(self):
        return (self.lat, self.lng) if self.has_point else None
