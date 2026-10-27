from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class BoostQuerySet(models.QuerySet):
    def active(self, at=None):
        at = at or timezone.now()
        return self.filter(starts_at__lte=at, ends_at__gt=at)


class Boost(TimeStampedModel):
    class Source(models.TextChoices):
        FREE = "free", _("Free")
        PAID = "paid", _("Paid")  # reserved; never used (no payment code)

    listing = models.ForeignKey("listings.Listing", on_delete=models.CASCADE, related_name="boosts")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="boosts"
    )
    source = models.CharField(max_length=4, choices=Source.choices, default=Source.FREE)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    used_bonus = models.BooleanField(default=False)
    end_notified = models.BooleanField(default=False)

    objects = BoostQuerySet.as_manager()

    class Meta:
        ordering = ["-starts_at"]
        indexes = [models.Index(fields=["starts_at", "ends_at"])]

    def __str__(self):
        return f"Boost of {self.listing_id} until {self.ends_at:%Y-%m-%d}"

    @property
    def is_active(self):
        now = timezone.now()
        return self.starts_at <= now < self.ends_at
