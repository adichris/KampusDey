"""Re-encrypt secrets with the first key in FIELD_ENCRYPTION_KEY (comma-separated, newest first)."""

from django.core.management.base import BaseCommand

from apps.sitesettings.fields import PREFIX, encrypt
from apps.sitesettings.models import IntegrationSettings

SECRET_FIELDS = ["sms_api_key", "sms_api_secret", "turnstile_secret", "geolite2_license_key"]


class Command(BaseCommand):
    help = "Rotate the Fernet key used for encrypted admin secrets."

    def handle(self, *args, **opts):
        obj = IntegrationSettings.load()
        updates = {}
        for name in SECRET_FIELDS:
            value = getattr(obj, name)
            if value:
                updates[name] = encrypt(value)
        if updates:
            IntegrationSettings.objects.filter(pk=obj.pk).update(**updates)
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {len(updates)} secrets (prefix {PREFIX})"))
