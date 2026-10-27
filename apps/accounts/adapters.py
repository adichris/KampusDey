from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_authenticated and not user.onboarded:
            return reverse("accounts:onboarding")
        return super().get_login_redirect_url(request)

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=commit)
        if commit:
            from apps.growth.services import attach_referral
            from apps.telemetry.services import record

            from .services import ensure_profile

            ensure_profile(user)
            attach_referral(request, user)
            record("signup", request=request, user=user)
        return user
