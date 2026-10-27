"""Account rules: permission helpers (interim rules), phone OTP, verification, deletion, export."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import timedelta

from constance import config
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.sitesettings.models import IntegrationSettings

from .models import PhoneOTP, Profile, User, VerificationRequest


@dataclass
class Decision:
    allowed: bool
    reason: str = ""

    def __bool__(self):
        return self.allowed


OK = Decision(True)


def _deny(reason):
    return Decision(False, reason)


def ensure_profile(user: User) -> Profile:
    profile, _created = Profile.objects.get_or_create(user=user)
    return profile


def phone_required() -> bool:
    return IntegrationSettings.get_cached().require_phone_verification


def _base(user) -> Decision:
    if user is None or not user.is_authenticated:
        return _deny(_("Log in first."))
    if not user.is_active:
        return _deny(_("Your account is disabled."))
    if not user.email_verified:
        return _deny(_("Verify your email address first."))
    return OK


def can_post(user) -> Decision:
    return _base(user)


def can_comment(user) -> Decision:
    return _base(user)


def can_like(user) -> Decision:
    return _base(user)


def can_chat(user) -> Decision:
    decision = _base(user)
    if not decision:
        return decision
    if phone_required() and not user.phone_verified:
        return _deny(_("Verify your phone number to chat."))
    return OK


def is_new_account(user) -> bool:
    return user.account_age_hours < config.CHAT_NEW_ACCOUNT_DAYS * 24


def can_message_first_time(user) -> Decision:
    """Starting a conversation with someone new."""
    decision = can_chat(user)
    if not decision:
        return decision
    if user.account_age_hours < config.FIRST_CONTACT_MIN_ACCOUNT_AGE_HOURS:
        return _deny(
            _("New accounts can message someone new after %(h)s hours.")
            % {"h": config.FIRST_CONTACT_MIN_ACCOUNT_AGE_HOURS}
        )
    return OK


def daily_message_limit_reached(user) -> bool:
    from apps.chat.models import Message

    if not is_new_account(user):
        return False
    since = timezone.now() - timedelta(days=1)
    sent = Message.objects.filter(sender=user, created_at__gte=since, kind="text").count()
    return sent >= config.CHAT_NEW_ACCOUNT_DAILY_LIMIT


def can_boost(user, listing=None) -> Decision:
    from apps.boosts.services import can_boost as boost_rules

    return boost_rules(user, listing)


# ---------------------------------------------------------------------------
# Phone OTP
# ---------------------------------------------------------------------------
class OTPError(Exception):
    pass


def request_otp(user: User, phone) -> PhoneOTP:
    from .sms import get_sms_backend

    last = PhoneOTP.objects.filter(user=user).order_by("-created_at").first()
    if last and (timezone.now() - last.created_at).total_seconds() < settings.OTP_RESEND_SECONDS:
        raise OTPError(_("Please wait a minute before requesting another code."))
    if User.objects.filter(phone=phone, phone_verified=True).exclude(pk=user.pk).exists():
        raise OTPError(_("That number is already verified on another account."))
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = PhoneOTP.objects.create(
        user=user,
        phone=phone,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
    )
    get_sms_backend().send(
        str(phone), _("Your KampusDey code is %(code)s. It expires in 10 minutes.") % {"code": code}
    )
    return otp


def verify_otp(user: User, code: str) -> bool:
    otp = PhoneOTP.objects.filter(user=user, used_at__isnull=True).order_by("-created_at").first()
    if otp is None:
        raise OTPError(_("Request a code first."))
    if otp.expires_at < timezone.now():
        raise OTPError(_("That code has expired. Request a new one."))
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise OTPError(_("Too many attempts. Request a new code."))
    otp.attempts += 1
    if not check_password((code or "").strip(), otp.code_hash):
        otp.save(update_fields=["attempts", "updated_at"])
        raise OTPError(_("That code is not correct."))
    otp.used_at = timezone.now()
    otp.save(update_fields=["attempts", "used_at", "updated_at"])
    user.phone = otp.phone
    user.phone_verified = True
    user.save(update_fields=["phone", "phone_verified"])
    return True


# ---------------------------------------------------------------------------
# Verification requests
# ---------------------------------------------------------------------------
BADGE_FIELDS = {
    VerificationRequest.Kind.STUDENT: "verified_student",
    VerificationRequest.Kind.LANDLORD: "verified_landlord",
    VerificationRequest.Kind.AGENT: "verified_agent",
}


@transaction.atomic
def decide_verification(request_obj: VerificationRequest, approve: bool, reviewer, note: str = ""):
    """Set the badge, then delete the document file and keep only the result (§5.1)."""
    from apps.notifications.services import notify

    profile = ensure_profile(request_obj.user)
    field = BADGE_FIELDS[request_obj.kind]
    if approve:
        setattr(profile, field, True)
        setattr(profile, f"{field}_at", timezone.now())
        profile.save()
    request_obj.status = (
        VerificationRequest.Status.APPROVED if approve else VerificationRequest.Status.REJECTED
    )
    request_obj.reviewed_by = reviewer
    request_obj.reviewed_at = timezone.now()
    request_obj.note = note
    if request_obj.document:
        request_obj.document.delete(save=False)
    request_obj.document = None
    request_obj.save()
    notify(
        request_obj.user,
        "verification",
        _("Your verification was approved") if approve else _("Your verification was not approved"),
        note,
        url="/accounts/profile/",
    )
    return request_obj


# ---------------------------------------------------------------------------
# Deletion and export
# ---------------------------------------------------------------------------
@transaction.atomic
def delete_account(user: User):
    """Anonymise listings/messages and remove personal data, then deactivate."""
    from allauth.account.models import EmailAddress
    from allauth.socialaccount.models import SocialAccount

    from apps.chat.models import Message
    from apps.contacts.models import ContactCard
    from apps.listings.models import Listing

    for listing in Listing.objects.filter(owner=user):
        for photo in listing.photos.all():
            photo.image.delete(save=False)
            photo.delete()
    Listing.objects.filter(owner=user).update(
        status=Listing.Status.ARCHIVED,
        contact_card=None,
        description="",
        title=_("Removed listing"),
    )
    Message.objects.filter(sender=user).update(body=_("[message removed]"))
    ContactCard.objects.filter(owner=user).delete()
    for vr in user.verification_requests.all():
        if vr.document:
            vr.document.delete(save=False)
    user.verification_requests.all().delete()
    user.phone_otps.all().delete()
    EmailAddress.objects.filter(user=user).delete()
    SocialAccount.objects.filter(user=user).delete()
    profile = ensure_profile(user)
    if profile.avatar:
        profile.avatar.delete(save=False)
    profile.bio = ""
    profile.level = ""
    profile.avatar = None
    profile.save()
    user.email = f"deleted-{user.pk}-{secrets.token_hex(4)}@deleted.invalid"
    user.display_name = ""
    user.phone = None
    user.phone_verified = False
    user.is_active = False
    user.is_anonymised = True
    user.set_unusable_password()
    user.save()


def export_data(user: User) -> str:
    from apps.chat.models import Message
    from apps.listings.models import Listing

    profile = ensure_profile(user)
    data = {
        "exported_at": timezone.now().isoformat(),
        "account": {
            "email": user.email,
            "display_name": user.display_name,
            "phone": str(user.phone) if user.phone else None,
            "phone_verified": user.phone_verified,
            "date_joined": user.date_joined.isoformat(),
            "theme": user.theme,
        },
        "profile": {
            "role": profile.role,
            "seller_type": profile.seller_type,
            "home_campus": str(profile.home_campus) if profile.home_campus else None,
            "home_town": str(profile.home_town) if profile.home_town else None,
            "followed_campuses": [str(c) for c in profile.followed_campuses.all()],
            "level": profile.level,
            "bio": profile.bio,
            "badges": {f: getattr(profile, f) for f in BADGE_FIELDS.values()},
        },
        "listings": [
            {
                "title": item.title,
                "section": item.section,
                "description": item.description,
                "price": str(item.price) if item.price is not None else None,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "url": item.get_absolute_url(),
            }
            for item in Listing.objects.filter(owner=user)
        ],
        "messages": [
            {
                "conversation": m.conversation_id,
                "body": m.body,
                "kind": m.kind,
                "sent_at": m.created_at.isoformat(),
            }
            for m in Message.objects.filter(sender=user).order_by("created_at")
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def alias_for(user: User, campus=None) -> str:
    profile = ensure_profile(user)
    if profile.role == Profile.Role.STUDENT and (campus or profile.home_campus):
        short = (campus or profile.home_campus).label
        return _("%(campus)s Student #%(n)s") % {"campus": short, "n": user.alias_number}
    return _("KampusDey User #%(n)s") % {"n": user.alias_number}
