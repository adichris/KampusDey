from allauth.account.signals import email_confirmed, user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from .middleware import PHONE_GATE_SESSION_KEY
from .models import User


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        from apps.notifications.models import NotificationPreference

        from .services import ensure_profile

        ensure_profile(instance)
        NotificationPreference.objects.get_or_create(
            user=instance,
            defaults={"email_triggers": NotificationPreference.default_email_triggers()},
        )


@receiver(user_logged_in)
def phone_gate_on_login(sender, request, user, **kwargs):
    from .services import phone_required

    if phone_required() and not user.phone_verified:
        request.session[PHONE_GATE_SESSION_KEY] = True
    # Carry a guest's campus choice over to a profile that has none yet.
    from apps.locations.services import adopt_guest_location

    adopt_guest_location(request, user)


@receiver(email_confirmed)
def on_email_confirmed(sender, request, email_address, **kwargs):
    from apps.growth.services import maybe_reward_referral

    maybe_reward_referral(email_address.user)
