from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    listing = models.ForeignKey(
        "listings.Listing", on_delete=models.CASCADE, related_name="conversations"
    )
    starter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="started_conversations"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_conversations"
    )
    starter_alias = models.CharField(max_length=60)
    owner_alias = models.CharField(max_length=60)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_blocked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["listing", "starter"], name="uniq_conversation")
        ]

    def __str__(self):
        return f"{self.starter_alias} ↔ {self.owner_alias} on {self.listing_id}"

    def get_absolute_url(self):
        return reverse("chat:detail", args=[self.pk])

    def other(self, user):
        return self.owner if user.pk == self.starter_id else self.starter

    def alias_for(self, user):
        return self.starter_alias if user.pk == self.starter_id else self.owner_alias

    def has_participant(self, user) -> bool:
        return user.pk in (self.starter_id, self.owner_id)


class Message(TimeStampedModel):
    class Kind(models.TextChoices):
        TEXT = "text", _("Text")
        SHARED_CONTACT = "shared_contact", _("Shared contact")
        SYSTEM = "system", _("System")

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    body = models.TextField(max_length=2000)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.TEXT)
    has_scam_warning = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return self.body[:40]


class Block(TimeStampedModel):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_made"
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_received"
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["blocker", "blocked"], name="uniq_block")]

    def __str__(self):
        return f"{self.blocker_id} blocked {self.blocked_id}"
