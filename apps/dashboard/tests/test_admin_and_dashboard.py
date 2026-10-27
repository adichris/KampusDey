import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from apps.telemetry.services import record
from tests import factories as f

pytestmark = pytest.mark.django_db
LOCAL_APPS = {c.label for c in apps.get_app_configs() if c.name.startswith("apps.")}


def test_every_local_model_is_registered_in_admin():
    missing = [
        m.__name__ for m in apps.get_models()
        if m._meta.app_label in LOCAL_APPS and not m._meta.abstract and m not in admin.site._registry
        and not m.__name__.endswith("Details")  # details models are inlines on Listing
        and m.__name__ != "Message"  # message bodies are readable only through a report (§6.8)
    ]
    assert not missing


def test_admin_dashboard_and_changelists_load(admin_client):
    listing = f.ListingFactory()
    record("view", listing=listing)
    f.PlaceFactory()
    assert admin_client.get(reverse("admin:index")).status_code == 200
    for model, model_admin in admin.site._registry.items():
        if model._meta.app_label not in LOCAL_APPS:
            continue
        url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
        assert admin_client.get(url, follow=True).status_code == 200, url
    assert admin_client.get(reverse("admin:locations_review_queue")).status_code == 200
    assert admin_client.get(reverse("admin:locations_duplicates")).status_code == 200
    assert admin_client.get(reverse("admin:listings_listing_change", args=[listing.pk])).status_code == 200


def test_constance_settings_editable_in_admin(admin_client):
    page = admin_client.get("/admin/constance/config/")
    assert page.status_code == 200
    for key in ("EXPIRY_NEEDS_CHECK_DAYS", "BOOSTS_PER_WEEK", "MAP_TILE_URL", "THEMES_OFFERED", "AMBASSADOR_BONUS_BOOSTS",
                "REMOTIVE_FETCHES_PER_DAY"):
        assert key.encode() in page.content


def test_staff_mfa_required(client, settings):
    settings.STAFF_MFA_REQUIRED = True
    staff = f.UserFactory(is_staff=True, is_superuser=True)
    client.force_login(staff)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302 and "/2fa/totp/activate/" in response.url


def test_poster_dashboard_and_stats(client_user, user):
    listing = f.ListingFactory(owner=user)
    assert client_user.get(reverse("dashboard:home")).status_code == 200
    assert client_user.get(reverse("dashboard:stats", args=[listing.pk])).status_code == 200
    client_user.post(reverse("dashboard:taken", args=[listing.pk]))
    listing.refresh_from_db()
    assert listing.status == "taken"
    client_user.post(reverse("dashboard:renew", args=[listing.pk]))
    listing.refresh_from_db()
    assert listing.status == "active"


FACTORIES = [name for name in dir(f) if name.endswith("Factory") and name not in ("DjangoModelFactory",)]


@pytest.mark.parametrize("name", FACTORIES)
def test_factory_builds_saved_instance_with_str(name):
    obj = getattr(f, name)()
    assert obj.pk and str(obj)
