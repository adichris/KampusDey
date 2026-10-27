import pytest


@pytest.fixture(autouse=True)
def _isolate(settings):
    """Reset in-process memos and caches between tests."""
    from django.core.cache import cache

    from apps.accounts.sms import ConsoleSMSBackend
    from apps.sitesettings import models as sitesettings_models

    sitesettings_models._MEMO["obj"] = None
    ConsoleSMSBackend.outbox.clear()
    cache.clear()
    settings.STAFF_MFA_REQUIRED = False
    yield
    sitesettings_models._MEMO["obj"] = None


@pytest.fixture
def user(db):
    from tests.factories import UserFactory

    return UserFactory()


@pytest.fixture
def campus(db):
    from tests.factories import CampusFactory

    return CampusFactory()


@pytest.fixture
def client_user(client, user):
    client.force_login(user)
    return client
