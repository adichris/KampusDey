from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Profile
from apps.locations.models import Campus

from . import services


def referral(request, code):
    profile = Profile.objects.filter(referral_code=code, is_ambassador=True).first()
    if profile:
        request.session[services.REF_SESSION_KEY] = code
    return redirect("account_signup")


def rent_check(request, campus_slug):
    campus = get_object_or_404(Campus.objects.visible(), slug=campus_slug)
    return render(request, "growth/rent_check.html", {"campus": campus, **services.rent_check(campus)})
