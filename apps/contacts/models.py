from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class ContactCard(TimeStampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_cards"
    )
    label = models.CharField(_("label"), max_length=60, default=_("Personal"))
    preferred_time = models.CharField(_("best time to contact"), max_length=80, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "label"]

    def __str__(self):
        return f"{self.label} ({self.owner})"

    def channel(self, kind):
        return next((c for c in self.channels.all() if c.kind == kind), None)


class ContactChannel(TimeStampedModel):
    class Kind(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        PHONE = "phone", _("Phone call")
        TELEGRAM = "telegram", "Telegram"
        EMAIL = "email", _("Email (relayed)")
        CHAT = "chat", _("In-app chat")

    card = models.ForeignKey(ContactCard, on_delete=models.CASCADE, related_name="channels")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    value = models.CharField(max_length=120, blank=True)
    is_verified = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["card", "kind"], name="uniq_card_channel_kind")
        ]

    def __str__(self):
        return f"{self.get_kind_display()} on {self.card_id}"
