import time

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

from .fields import EncryptedTextField

# In-process memo only: never put decrypted secrets into a shared cache backend.
_MEMO: dict = {"obj": None, "at": 0.0}
MEMO_SECONDS = 30


class IntegrationSettings(TimeStampedModel):
    """Singleton with third-party settings. Secret fields are encrypted at rest."""

    class SMSProvider(models.TextChoices):
        NONE = "none", _("None")
        CONSOLE = "console", _("Console (development)")
        HUBTEL = "hubtel", "Hubtel"
        ARKESEL = "arkesel", "Arkesel"
        MNOTIFY = "mnotify", "mNotify"
        OTHER = "other", _("Other")

    sms_provider = models.CharField(max_length=10, choices=SMSProvider.choices, default="console")
    sms_api_key = EncryptedTextField(blank=True, default="")
    sms_api_secret = EncryptedTextField(blank=True, default="")
    sms_sender_id = models.CharField(max_length=11, blank=True, default="KampusDey")
    require_phone_verification = models.BooleanField(
        default=False, help_text=_("Users must verify a phone before boosting or chatting")
    )
    turnstile_site_key = models.CharField(max_length=100, blank=True, default="")
    turnstile_secret = EncryptedTextField(blank=True, default="")
    geolite2_account_id = models.CharField(max_length=20, blank=True, default="")
    geolite2_license_key = EncryptedTextField(blank=True, default="")
    geolite2_last_updated = models.DateTimeField(null=True, blank=True)
    umami_script_url = models.URLField(blank=True, default="")
    umami_website_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = _("integration settings")
        verbose_name_plural = _("integration settings")

    def __str__(self):
        return str(_("Integration settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        _MEMO["obj"] = None

    @classmethod
    def load(cls) -> "IntegrationSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def get_cached(cls) -> "IntegrationSettings":
        obj = _MEMO["obj"]
        if obj is None or time.monotonic() - _MEMO["at"] > MEMO_SECONDS:
            try:
                obj = cls.load()
            except Exception:  # table missing during first migrate
                return cls()
            _MEMO.update(obj=obj, at=time.monotonic())
        return obj


class SectionAvailability(TimeStampedModel):
    """Per-campus (or global when campus is null) section switch (§5.12)."""

    section = models.CharField(max_length=20)
    campus = models.ForeignKey(
        "locations.Campus", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = _("section availability")
        constraints = [
            models.UniqueConstraint(fields=["section", "campus"], name="uniq_section_campus"),
            models.UniqueConstraint(
                fields=["section"],
                condition=models.Q(campus__isnull=True),
                name="uniq_section_global",
            ),
        ]

    def __str__(self):
        where = self.campus or _("all campuses")
        return f"{self.section} @ {where}: {'on' if self.enabled else 'off'}"
