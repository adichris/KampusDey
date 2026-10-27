from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

PHONE_GATE_SESSION_KEY = "kd_phone_gate"
SAFE_PREFIXES = ("/static/", "/media/", "/accounts/", "/sw.js", "/manifest.webmanifest", "/i18n/")


class AccountGatesMiddleware:
    """Staff MFA enforcement and the 'verify your phone at next login' prompt."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            response = self._staff_mfa(request, user) or self._phone_gate(request, user)
            if response:
                return response
        return self.get_response(request)

    def _staff_mfa(self, request, user):
        if not getattr(settings, "STAFF_MFA_REQUIRED", True) or not user.is_staff:
            return None
        if not request.path.startswith("/" + settings.ADMIN_URL):
            return None
        from allauth.mfa.models import Authenticator

        if Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists():
            return None
        return redirect(reverse("mfa_activate_totp") + "?next=" + request.path)

    def _phone_gate(self, request, user):
        if not request.session.get(PHONE_GATE_SESSION_KEY):
            return None
        if user.phone_verified:
            request.session.pop(PHONE_GATE_SESSION_KEY, None)
            return None
        if request.path.startswith(SAFE_PREFIXES) or request.method != "GET" or request.htmx:
            return None
        return redirect("accounts:phone")
