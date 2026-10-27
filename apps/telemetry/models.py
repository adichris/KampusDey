from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Event(models.Model):
    """Raw telemetry event. No IP addresses: sessions are hashed (§5.10)."""

    class Kind(models.TextChoices):
        VIEW = "view", _("View")
        TAP = "tap", _("Contact tap")
        LIKE = "like", _("Like")
        UNLIKE = "unlike", _("Unlike")
        SHARE = "share", _("Share")
        SEARCH = "search", _("Search")
        BOOST = "boost", _("Boost")
        SIGNUP = "signup", _("Sign-up")
        POST = "post", _("Post published")

    kind = models.CharField(max_length=8, choices=Kind.choices)
    listing = models.ForeignKey("listings.Listing", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    session_hash = models.CharField(max_length=64, blank=True)
    campus = models.ForeignKey("locations.Campus", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    town = models.ForeignKey("locations.Town", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    section = models.CharField(max_length=20, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kind", "created_at"], name="event_kind_created"),
            models.Index(fields=["listing", "created_at"], name="event_listing_created"),
        ]

    def __str__(self):
        return f"{self.kind} @ {self.created_at:%Y-%m-%d %H:%M}"


class DailyListingStats(models.Model):
    listing = models.ForeignKey("listings.Listing", on_delete=models.CASCADE, related_name="daily_stats")
    date = models.DateField()
    views = models.PositiveIntegerField(default=0)
    taps = models.PositiveIntegerField(default=0)
    taps_by_channel = models.JSONField(default=dict, blank=True)
    likes = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = _("daily listing stats")
        constraints = [models.UniqueConstraint(fields=["listing", "date"], name="uniq_listing_day")]

    def __str__(self):
        return f"{self.listing_id} {self.date}"


class DailyCampusStats(models.Model):
    campus = models.ForeignKey("locations.Campus", on_delete=models.CASCADE, related_name="daily_stats")
    date = models.DateField()
    signups = models.PositiveIntegerField(default=0)
    posts = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    taps = models.PositiveIntegerField(default=0)
    searches = models.PositiveIntegerField(default=0)
    zero_result_searches = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = _("daily campus stats")
        constraints = [models.UniqueConstraint(fields=["campus", "date"], name="uniq_campus_day")]

    def __str__(self):
        return f"{self.campus_id} {self.date}"


class PendingEvent(models.Model):
    """Database fallback buffer used when Redis is not configured."""

    payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"pending {self.pk}"
