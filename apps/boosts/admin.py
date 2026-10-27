from django.contrib import admin

from apps.core.admin_base import KDModelAdmin

from .models import Boost


@admin.register(Boost)
class BoostAdmin(KDModelAdmin):
    list_display = ["listing", "user", "source", "starts_at", "ends_at", "used_bonus"]
    list_filter = ["source", "used_bonus"]
    search_fields = ["listing__title", "user__email"]
    autocomplete_fields = ["listing", "user"]
    readonly_fields = ["source"]
