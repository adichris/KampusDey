"""Remove secret values that the audit log recorded for IntegrationSettings.

Until the exclusion list was derived from the model, saving SMTP, S3 or Google secrets in the
admin stored their decrypted values in auditlog entries. This deletes those keys from every
IntegrationSettings log entry (the entry itself, who changed what and when, is kept).
"""

import json

from django.db import migrations

SECRETS = {
    "sms_api_key",
    "sms_api_secret",
    "turnstile_secret",
    "geolite2_license_key",
    "smtp_password",
    "s3_secret_access_key",
    "google_client_secret",
}


def _clean(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value, False
        cleaned, changed = _clean(value)
        return (json.dumps(cleaned) if changed else value), changed
    if isinstance(value, dict):
        changed = False
        out = {}
        for key, item in value.items():
            if key in SECRETS:
                changed = True
                continue
            new, sub = _clean(item)
            changed = changed or sub
            out[key] = new
        return out, changed
    if isinstance(value, list):
        changed = False
        out = []
        for item in value:
            new, sub = _clean(item)
            changed = changed or sub
            out.append(new)
        return out, changed
    return value, False


def scrub(apps, schema_editor):
    try:
        LogEntry = apps.get_model("auditlog", "LogEntry")
    except LookupError:
        return
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(app_label="sitesettings", model="integrationsettings").first()
    if ct is None:
        return
    for entry in LogEntry.objects.filter(content_type=ct).iterator():
        fields = []
        for name in ("changes", "serialized_data", "additional_data"):
            if not hasattr(entry, name):
                continue
            new, changed = _clean(getattr(entry, name))
            if changed:
                setattr(entry, name, new)
                fields.append(name)
        text = getattr(entry, "changes_text", "") or ""
        if any(secret in text for secret in SECRETS):
            entry.changes_text = ""
            fields.append("changes_text")
        if fields:
            entry.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [
        ("sitesettings", "0002_email_storage_google"),
        ("auditlog", "0017_add_actor_email"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(scrub, migrations.RunPython.noop)]
