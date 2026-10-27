from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import User, VerificationRequest
from apps.accounts.sms import ConsoleSMSBackend
from apps.sitesettings.models import IntegrationSettings
from tests.factories import ListingFactory, MessageFactory, UserFactory, VerificationRequestFactory

pytestmark = pytest.mark.django_db


def test_unverified_users_cannot_post_comment_like_chat():
    user = UserFactory(verified=False)
    for check in (services.can_post, services.can_comment, services.can_like, services.can_chat):
        assert not check(user)
    verified = UserFactory()
    assert services.can_post(verified) and services.can_like(verified)


def test_first_contact_needs_account_age():
    young = UserFactory(date_joined=timezone.now() - timedelta(hours=2))
    assert not services.can_message_first_time(young)
    old = UserFactory(date_joined=timezone.now() - timedelta(days=2))
    assert services.can_message_first_time(old)


def test_new_account_daily_message_limit(settings):
    from constance import config

    user = UserFactory(date_joined=timezone.now() - timedelta(days=1))
    config.CHAT_NEW_ACCOUNT_DAILY_LIMIT = 2
    MessageFactory.create_batch(2, sender=user)
    assert services.daily_message_limit_reached(user)
    old = UserFactory(date_joined=timezone.now() - timedelta(days=30))
    MessageFactory.create_batch(3, sender=old)
    assert not services.daily_message_limit_reached(old)


def _require_phone():
    integ = IntegrationSettings.load()
    integ.require_phone_verification = True
    integ.sms_provider = "console"
    integ.save()


def test_phone_switch_blocks_chat_and_forces_otp_prompt(client):
    _require_phone()
    user = UserFactory()
    assert not services.can_chat(user)
    client.post(reverse("account_login"), {"login": user.email, "password": "pass12345!"})
    response = client.get("/")
    assert response.status_code == 302 and response.url == reverse("accounts:phone")


def test_otp_flow_console_backend():
    _require_phone()
    user = UserFactory()
    services.request_otp(user, "+233241234567")
    to, message = ConsoleSMSBackend.outbox[-1]
    code = message.split("code is ")[1][:6]
    with pytest.raises(services.OTPError):
        services.verify_otp(user, "000000" if code != "000000" else "111111")
    assert services.verify_otp(user, code)
    user.refresh_from_db()
    assert user.phone_verified and str(user.phone) == "+233241234567"
    assert services.can_chat(user)


def test_otp_max_attempts_and_resend_wait():
    user = UserFactory()
    services.request_otp(user, "+233241234567")
    with pytest.raises(services.OTPError):
        services.request_otp(user, "+233241234567")  # resend after 60 s only
    for _ in range(3):
        with pytest.raises(services.OTPError):
            services.verify_otp(user, "abcdef")
    with pytest.raises(services.OTPError, match="Too many"):
        services.verify_otp(user, "123456")


def test_otp_expiry():
    user = UserFactory()
    otp = services.request_otp(user, "+233241234567")
    otp.expires_at = timezone.now() - timedelta(seconds=1)
    otp.save()
    with pytest.raises(services.OTPError, match="expired"):
        services.verify_otp(user, "123456")


def test_verification_document_deleted_after_decision():
    admin = UserFactory(is_staff=True)
    req = VerificationRequestFactory()
    storage, name = req.document.storage, req.document.name
    assert storage.exists(name)
    services.decide_verification(req, True, admin)
    req.refresh_from_db()
    assert not storage.exists(name) and not req.document
    assert req.status == VerificationRequest.Status.APPROVED
    assert req.user.profile.verified_student


def test_rejected_verification_also_deletes_document():
    req = VerificationRequestFactory()
    storage, name = req.document.storage, req.document.name
    services.decide_verification(req, False, None, "Unclear photo")
    assert not storage.exists(name)
    assert not req.user.profile.verified_student


def test_account_deletion_anonymises():
    user = UserFactory(phone="+233241234567")
    listing = ListingFactory(owner=user)
    MessageFactory(sender=user, body="my secret")
    services.delete_account(user)
    user.refresh_from_db()
    listing.refresh_from_db()
    assert not user.is_active and user.is_anonymised and user.phone is None
    assert "deleted" in user.email and user.display_name == ""
    assert listing.status == "archived" and listing.description == ""
    from apps.chat.models import Message

    assert not Message.objects.filter(body="my secret").exists()


def test_export_contains_profile_listings_messages():
    import json

    user = UserFactory()
    ListingFactory(owner=user, title="Exported thing")
    MessageFactory(sender=user, body="hi there")
    data = json.loads(services.export_data(user))
    assert data["account"]["email"] == user.email
    assert data["listings"][0]["title"] == "Exported thing"
    assert data["messages"][0]["body"] == "hi there"


def test_secrets_unreadable_in_database():
    from django.db import connection

    integ = IntegrationSettings.load()
    integ.sms_api_key = "super-secret-key"
    integ.save()
    with connection.cursor() as cur:
        cur.execute("SELECT sms_api_key FROM sitesettings_integrationsettings WHERE id = 1")
        raw = cur.fetchone()[0]
    assert "super-secret-key" not in raw and raw.startswith("fernet:")
    assert IntegrationSettings.load().sms_api_key == "super-secret-key"


def test_theme_persistence_for_users(client_user, user):
    assert client_user.post(reverse("accounts:theme"), {"theme": "dracula"}).status_code == 204
    user.refresh_from_db()
    assert user.theme == "dracula"
    html = client_user.get("/").content.decode()
    assert 'data-user-theme="dracula"' in html and 'data-theme="dracula"' in html


def test_theme_rejects_unknown(client_user):
    assert client_user.post(reverse("accounts:theme"), {"theme": "hotpink"}).status_code == 400


def test_guest_theme_script_present(client, db):
    html = client.get("/").content.decode()
    assert "kd-theme" in html and "prefers-color-scheme" in html


def test_onboarding_sets_profile_and_location(client, campus):
    user = UserFactory(onboarded=False)
    client.force_login(user)
    response = client.post(
        reverse("accounts:onboarding"),
        {"display_name": "Ama", "role": "student", "home_campus": campus.pk, "level": "200"},
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.onboarded and user.profile.home_campus == campus


def test_alias_for_student_uses_campus(campus):
    user = UserFactory()
    user.profile.home_campus = campus
    user.profile.save()
    assert services.alias_for(user).startswith(f"{campus.label} Student #")
    user.profile.role = "landlord"
    user.profile.save()
    assert services.alias_for(user).startswith("KampusDey User #")


def test_signup_requires_email_verification(client, db):
    client.post(
        reverse("account_signup"),
        {
            "email": "new@example.test",
            "password1": "Very-long-pass-123",
            "password2": "Very-long-pass-123",
        },
    )
    user = User.objects.get(email="new@example.test")
    assert not user.email_verified
    assert hasattr(user, "profile")


def test_profile_pages_render(client_user):
    for name in (
        "accounts:profile",
        "accounts:edit_profile",
        "accounts:appearance",
        "accounts:phone",
        "accounts:verification",
        "accounts:delete",
    ):
        assert client_user.get(reverse(name)).status_code == 200
    assert client_user.get(reverse("accounts:export"))["Content-Type"].startswith(
        "application/json"
    )
