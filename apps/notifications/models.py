from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Trigger(models.TextChoices):
    MESSAGE = "message", _("New message")
    COMMENT = "comment", _("New comment or question")
    REPLY = "reply", _("Reply to your question")
    SAVED_SEARCH = "saved_search", _("Saved search match")
    STILL_AVAILABLE = "still_available", _("'Still available?' check")
    BOOST_ENDED = "boost_ended", _("Boost ended")
    VERIFICATION = "verification", _("Verification decision")
    CAMPUS_REQUEST = "campus_request", _("Campus request result")
    CLAIM = "claim", _("Place claim decision")
    REFERRAL = "referral", _("Referral reward")


class Notification(TimeStampedModel):
    """In-app notification. Implemented in-house instead of django-notifications-hq (see PROGRESS)."""

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    trigger = models.CharField(max_length=16, choices=Trigger.choices)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=400, blank=True)
    url = models.CharField(max_length=300, blank=True)
    data = models.JSONField(default=dict, blank=True, help_text=_("Extra links for the email, e.g. one-tap"))
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    email_skipped = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"]), models.Index(fields=["emailed_at", "email_skipped"])]

    def __str__(self):
        return self.title


class NotificationPreference(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_prefs")
    email_triggers = models.JSONField(default=list, blank=True, help_text=_("Triggers that also send email"))
    weekly_digest = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"Preferences of {self.user_id}"

    @classmethod
    def default_email_triggers(cls):
        return [t.value for t in Trigger]

    def wants_email(self, trigger: str) -> bool:
        return trigger in (self.email_triggers or [])
