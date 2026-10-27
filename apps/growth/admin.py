from django.contrib import admin

from apps.core.admin_base import KDModelAdmin

from .models import Referral, Spotlight


@admin.register(Referral)
class ReferralAdmin(KDModelAdmin):
    list_display = ["ambassador", "referred_user", "rewarded", "created_at"]
    list_filter = ["rewarded"]
    autocomplete_fields = ["ambassador", "referred_user"]


@admin.register(Spotlight)
class SpotlightAdmin(KDModelAdmin):
    list_display = ["week_start", "campus", "listing", "user", "blurb"]
    autocomplete_fields = ["listing", "user", "campus"]
