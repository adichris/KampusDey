from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Like(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="likes")
    listing = models.ForeignKey("listings.Listing", on_delete=models.CASCADE, related_name="likes")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "listing"], name="uniq_like")]

    def __str__(self):
        return f"{self.user_id} ♥ {self.listing_id}"


class Comment(TimeStampedModel):
    listing = models.ForeignKey("listings.Listing", on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    body = models.TextField(max_length=1000, help_text=_("Stored masked"))
    is_owner_reply = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.body[:40]


class Review(TimeStampedModel):
    class Status(models.TextChoices):
        VISIBLE = "visible", _("Visible")
        HIDDEN = "hidden", _("Hidden")

    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_given")
    hostel = models.ForeignKey("hostels.Hostel", on_delete=models.CASCADE, null=True, blank=True, related_name="reviews")
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="reviews_received"
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    body = models.TextField(max_length=1000, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.VISIBLE)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["reviewer", "hostel"], name="uniq_review_hostel",
                                    condition=models.Q(hostel__isnull=False)),
            models.UniqueConstraint(fields=["reviewer", "target_user"], name="uniq_review_user",
                                    condition=models.Q(target_user__isnull=False)),
        ]

    def __str__(self):
        return f"{self.rating}★ by {self.reviewer_id}"


class Report(TimeStampedModel):
    class Reason(models.TextChoices):
        SCAM = "scam", _("Scam or fraud")
        FAKE_LISTING = "fake_listing", _("Fake listing")
        WRONG_PRICE = "wrong_price", _("Wrong price")
        OFFENSIVE = "offensive", _("Offensive")
        SPAM = "spam", _("Spam")
        DUPLICATE = "duplicate", _("Duplicate")
        CLOSED = "closed", _("Closed (places)")
        WRONG_LOCATION = "wrong_location", _("Wrong location (places)")
        NOT_REAL = "not_real", _("Not a real place (places)")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        ACTIONED = "actioned", _("Actioned")
        DISMISSED = "dismissed", _("Dismissed")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="reports_made")
    reason = models.CharField(max_length=16, choices=Reason.choices)
    details = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id", "status"])]

    def __str__(self):
        return f"{self.get_reason_display()} on {self.content_type.model} #{self.object_id}"


class SavedSearch(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches")
    params = models.JSONField(default=dict, blank=True)
    campus = models.ForeignKey("locations.Campus", on_delete=models.CASCADE, null=True, blank=True)
    town = models.ForeignKey("locations.Town", on_delete=models.CASCADE, null=True, blank=True)
    section = models.CharField(max_length=20, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Saved search {self.section} for {self.user_id}"
