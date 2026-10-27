from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Referral(TimeStampedModel):
    ambassador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals"
    )
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referred_by"
    )
    rewarded = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ambassador_id} → {self.referred_user_id}"


class Spotlight(TimeStampedModel):
    listing = models.ForeignKey("listings.Listing", on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    campus = models.ForeignKey("locations.Campus", on_delete=models.CASCADE, null=True, blank=True)
    week_start = models.DateField()
    blurb = models.CharField(max_length=200, default=_("Student Business of the Week"))

    class Meta:
        ordering = ["-week_start"]

    def __str__(self):
        return f"Spotlight {self.week_start}"
