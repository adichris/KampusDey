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
    html = admin_client.get(
        f"/admin/sitesettings/integrationsettings/{integ.pk}/change/"
    ).content.decode()
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
    settings.FIELD_ENCRYPTION_KEY = (
        Fernet.generate_key().decode() + "," + settings.FIELD_ENCRYPTION_KEY
    )
    call_command("rotate_field_keys")
    settings.FIELD_ENCRYPTION_KEY = settings.FIELD_ENCRYPTION_KEY.split(",")[0]
    assert IntegrationSettings.load().sms_api_key == "abc"


def test_storage_is_local_until_s3_is_configured(settings, tmp_path):
    from apps.core.storage import SwitchingStorage, media_on_s3

    settings.MEDIA_ROOT = tmp_path
    settings.AWS_STORAGE_BUCKET_NAME = ""
    storage = SwitchingStorage()
    assert not media_on_s3() and storage.is_local
    name = storage.save("x/hello.txt", __import__("io").BytesIO(b"hi"))
    assert (tmp_path / name).exists() and storage.url(name) == f"/media/{name}"
    integ = IntegrationSettings.load()
    integ.s3_bucket = "kd-public"
    integ.s3_access_key_id = "AKIA"
    integ.s3_secret_access_key = "secret"
    integ.s3_custom_domain = "media.example.test"
    integ.save()
    assert media_on_s3() and not storage.is_local
    assert storage.url("a/b.jpg") == "https://media.example.test/a/b.jpg"
    assert SwitchingStorage(private=True).is_local  # no private bucket: stays on disk


def test_env_s3_is_used_when_admin_is_empty(settings):
    from apps.core.storage import s3_config

    settings.AWS_STORAGE_BUCKET_NAME = "env-bucket"
    settings.STORAGE_BACKEND = "auto"
    assert s3_config()["bucket_name"] == "env-bucket"
    settings.STORAGE_BACKEND = "local"
    assert s3_config() is None


def test_local_media_is_served_with_safe_headers(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "a.txt").write_text("hello")
    r = client.get("/media/p/a.txt")
    assert r.status_code == 200 and r["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in r["Content-Security-Policy"] and "immutable" in r["Cache-Control"]
    assert client.get("/media/../settings.py").status_code in (400, 404)
    settings.SERVE_MEDIA = False
    assert client.get("/media/p/a.txt").status_code == 404


def test_admin_smtp_settings_drive_email(settings):
    from apps.core.mail import ConfiguredEmailBackend

    settings.EMAIL_FALLBACK_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    backend = ConfiguredEmailBackend()
    assert "locmem" in type(backend.inner).__module__
    integ = IntegrationSettings.load()
    integ.smtp_host = "smtp.example.test"
    integ.smtp_username = "u"
    integ.smtp_password = "p"
    integ.email_from = "KampusDey <hi@example.test>"
    integ.save()
    backend = ConfiguredEmailBackend()
    assert backend.inner.host == "smtp.example.test" and backend.inner.password == "p"


def test_google_keys_from_admin_create_social_app(settings):
    from allauth.socialaccount.models import SocialApp

    from apps.sitesettings.services import sync_google_app

    settings.GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_SECRET = ""
    integ = IntegrationSettings.load()
    integ.google_client_id, integ.google_client_secret = "cid", "csecret"
    integ.save()
    sync_google_app(integ)
    assert SocialApp.objects.get(provider="google").client_id == "cid"
    integ.google_client_id = ""
    integ.save()
    sync_google_app(integ)
    assert not SocialApp.objects.filter(provider="google").exists()


def test_settings_overview_page(admin_client, client_user):
    page = admin_client.get("/admin/overview/")
    assert page.status_code == 200
    for text in (b"File storage", b"Email", b"Sign-in", b"Server"):
        assert text in page.content
    assert client_user.get("/admin/overview/").status_code in (302, 403)
