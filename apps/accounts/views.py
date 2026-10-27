from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.locations.services import set_location

from . import services
from .forms import DeleteAccountForm, OnboardingForm, OTPForm, PhoneForm, ProfileForm, VerificationForm
from .middleware import PHONE_GATE_SESSION_KEY
from .models import Profile, User


@login_required
def after_login(request):
    if not request.user.onboarded:
        return redirect("accounts:onboarding")
    return redirect(request.GET.get("next") or "/")


@login_required
def onboarding(request):
    profile = services.ensure_profile(request.user)
    location = request.location
    initial = {
        "display_name": request.user.display_name,
        "role": profile.role,
        "seller_type": profile.seller_type or "",
        "home_campus": location.campus,
        "home_town": None if location.campus else location.town,
        "level": profile.level,
    }
    form = OnboardingForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        request.user.display_name = data["display_name"]
        request.user.onboarded = True
        request.user.save(update_fields=["display_name", "onboarded"])
        profile.role = data["role"]
        profile.seller_type = data["seller_type"] or None
        profile.level = data["level"]
        profile.save()
        response = redirect("/")
        set_location(request, response, campus=data["home_campus"], town=data["home_town"])
        messages.success(request, _("Welcome to KampusDey!"))
        return response
    return render(request, "accounts/onboarding.html", {"form": form})


@login_required
def profile(request):
    from apps.boosts.services import boosts_left
    from apps.growth.services import ensure_referral_code

    prof = services.ensure_profile(request.user)
    if prof.is_ambassador:
        ensure_referral_code(prof)
    return render(
        request,
        "accounts/profile.html",
        {
            "profile": prof,
            "boosts_left": boosts_left(request.user),
            "phone_required": services.phone_required(),
            "verifications": request.user.verification_requests.all()[:5],
        },
    )


@login_required
def edit_profile(request):
    prof = services.ensure_profile(request.user)
    form = ProfileForm(request.POST or None, request.FILES or None, instance=prof,
                       initial={"display_name": request.user.display_name})
    if request.method == "POST" and form.is_valid():
        avatar = form.cleaned_data.get("avatar")
        obj = form.save(commit=False)
        if avatar and hasattr(avatar, "read"):
            from django.core.exceptions import ValidationError

            from apps.core.images import clean_image

            try:
                content, *_rest = clean_image(avatar, 5)
                obj.avatar.save(content.name, content, save=False)
            except ValidationError as exc:
                form.add_error("avatar", exc)
                return render(request, "accounts/edit_profile.html", {"form": form})
        obj.save()
        request.user.display_name = form.cleaned_data["display_name"]
        request.user.save(update_fields=["display_name"])
        messages.success(request, _("Profile saved."))
        return redirect("accounts:profile")
    return render(request, "accounts/edit_profile.html", {"form": form})


@login_required
def appearance(request):
    return render(request, "accounts/appearance.html")


@require_POST
def set_theme(request):
    from constance import config

    theme = request.POST.get("theme", "system")
    offered = [t.strip() for t in config.THEMES_OFFERED.split(",")]
    if theme not in offered:
        return HttpResponse(status=400)
    if request.user.is_authenticated:
        request.user.theme = theme
        request.user.save(update_fields=["theme"])
    return HttpResponse(status=204)


@login_required
@ratelimit(key="user", rate="10/h", method="POST", block=True)
@ratelimit(key="ip", rate="20/h", method="POST", block=True)
def phone(request):
    phone_form = PhoneForm(request.POST if "send" in request.POST else None)
    otp_form = OTPForm(request.POST if "verify" in request.POST else None)
    if request.method == "POST":
        if "skip" in request.POST:
            request.session.pop(PHONE_GATE_SESSION_KEY, None)
            return redirect("/")
        if "send" in request.POST and phone_form.is_valid():
            try:
                services.request_otp(request.user, phone_form.cleaned_data["phone"])
                messages.success(request, _("We sent a 6-digit code by SMS."))
            except services.OTPError as exc:
                messages.error(request, str(exc))
            return redirect("accounts:phone")
        if "verify" in request.POST and otp_form.is_valid():
            try:
                services.verify_otp(request.user, otp_form.cleaned_data["code"])
            except services.OTPError as exc:
                otp_form.add_error("code", str(exc))
            else:
                request.session.pop(PHONE_GATE_SESSION_KEY, None)
                messages.success(request, _("Phone number verified."))
                return redirect("accounts:profile")
    pending = request.user.phone_otps.filter(used_at__isnull=True).first()
    return render(request, "accounts/phone.html", {"phone_form": phone_form, "otp_form": otp_form, "pending": pending,
                                                   "required": services.phone_required()})


@login_required
def verification(request):
    form = VerificationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, _("Thanks! We'll review your document and then delete it."))
        return redirect("accounts:profile")
    return render(request, "accounts/verification.html", {"form": form})


@login_required
def delete_account(request):
    form = DeleteAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        logout(request)
        services.delete_account(user)
        messages.success(request, _("Your account was deleted. Goodbye!"))
        return redirect("/")
    return render(request, "accounts/delete.html", {"form": form})


@login_required
def export_data(request):
    data = services.export_data(request.user)
    response = HttpResponse(data, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="kampusdey-data.json"'
    return response


def public_profile(request, pk):
    from apps.engagement.models import Review
    from apps.engagement.services import can_review_user
    from apps.listings.selectors import visible_listings

    user = get_object_or_404(User.objects.select_related("profile"), pk=pk, is_active=True)
    listings = visible_listings(request.user).filter(owner=user)[:24]
    reviews = Review.objects.filter(target_user=user, status="visible").select_related("reviewer")[:20]
    return render(
        request,
        "accounts/public_profile.html",
        {"person": user, "profile": getattr(user, "profile", None) or Profile(user=user), "listings": listings,
         "reviews": reviews, "can_review": can_review_user(request.user, user)},
    )
