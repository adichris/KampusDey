from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class BannedTerm(TimeStampedModel):
    class Action(models.TextChoices):
        BLOCK = "block", _("Block")
        REVIEW = "review", _("Send to review")
        WARN = "warn", _("Show scam warning")

    class AppliesTo(models.TextChoices):
        LISTING = "listing", _("Listings")
        COMMENT = "comment", _("Comments")
        MESSAGE = "message", _("Messages")
        ALL = "all", _("Everything")

    term = models.CharField(max_length=200)
    is_regex = models.BooleanField(default=False)
    action = models.CharField(max_length=6, choices=Action.choices, default=Action.REVIEW)
    applies_to = models.CharField(max_length=8, choices=AppliesTo.choices, default=AppliesTo.ALL)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["term"]
        constraints = [
            models.UniqueConstraint(fields=["term", "applies_to"], name="uniq_banned_term")
        ]

    def __str__(self):
        return self.term


class ModerationItem(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    reason = models.CharField(max_length=300)
    auto = models.BooleanField(default=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.content_type.model} #{self.object_id}: {self.reason}"


class ScamAlert(TimeStampedModel):
    name = models.CharField(max_length=120, help_text=_("Name or alias the scammer uses"))
    phone_last4 = models.CharField(max_length=4, blank=True)
    description = models.TextField(max_length=2000)
    evidence_note = models.TextField(blank=True, help_text=_("Admin only, never shown publicly"))
    confirmed_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["-confirmed_at", "-created_at"]

    def __str__(self):
        return self.name


class PriceRangeSuggestion(TimeStampedModel):
    """Monthly suggestion from KampusDey's own listings; never applied automatically."""

    category_kind = models.CharField(
        max_length=10, choices=[("item", "Item"), ("service", "Service")]
    )
    category_id = models.PositiveBigIntegerField()
    category_name = models.CharField(max_length=80)
    suggested_min = models.DecimalField(max_digits=12, decimal_places=2)
    suggested_max = models.DecimalField(max_digits=12, decimal_places=2)
    samples = models.PositiveIntegerField()
    accepted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.category_name}: {self.suggested_min}–{self.suggested_max}"
