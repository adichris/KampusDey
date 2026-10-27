import pytest

from apps.sitesettings.models import IntegrationSettings, SectionAvailability
from apps.sitesettings.services import enabled_section_slugs, section_enabled
from tests import factories as f

pytestmark = pytest.mark.django_db


def test_section_resolution_campus_then_global_then_default(campus):
    assert section_enabled("rooms", campus) and not section_enabled("trips", campus)
    SectionAvailability.objects.create(section="trips", campus=None, enabled=True)
    assert section_enabled("trips", campus)
    SectionAvailability.objects.create(section="trips", campus=campus, enabled=False)
    assert not section_enabled("trips", campus) and section_enabled("trips", f.CampusFactory())
    assert "trips" not in enabled_section_slugs(campus)


def test_integration_admin_never_shows_secrets(admin_client):
    integ = IntegrationSettings.load()
    integ.turnstile_secret = "very-secret-value"
    integ.save()
    html = admin_client.get(f"/admin/sitesettings/integrationsettings/{integ.pk}/change/").content.decode()
    assert "very-secret-value" not in html and "•••• set" in html


def test_matrix_view(admin_client, campus):
    assert admin_client.get("/admin/sitesettings/sectionavailability/matrix/").status_code == 200
    data = {f"all:{s}": "on" for s in ("rooms", "jobs")}
    admin_client.post("/admin/sitesettings/sectionavailability/matrix/", data)
    assert not section_enabled("buy-sell") and section_enabled("rooms")


def test_rotate_field_keys(settings):
    from cryptography.fernet import Fernet
    from django.core.management import call_command

    integ = IntegrationSettings.load()
    integ.sms_api_key = "abc"
    integ.save()
    settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode() + "," + settings.FIELD_ENCRYPTION_KEY
    call_command("rotate_field_keys")
    settings.FIELD_ENCRYPTION_KEY = settings.FIELD_ENCRYPTION_KEY.split(",")[0]
    assert IntegrationSettings.load().sms_api_key == "abc"
