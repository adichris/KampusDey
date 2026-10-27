from django.contrib import admin

from apps.core.admin_base import KDModelAdmin

from .models import DailyCampusStats, DailyListingStats, Event, PendingEvent


class ReadOnly(KDModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Event)
class EventAdmin(ReadOnly):
    list_display = ["kind", "listing", "campus", "section", "created_at"]
    list_filter = ["kind", "section"]
    date_hierarchy = "created_at"


@admin.register(DailyListingStats)
class DailyListingStatsAdmin(ReadOnly):
    list_display = ["listing", "date", "views", "taps", "likes", "shares", "comments"]
    date_hierarchy = "date"


@admin.register(DailyCampusStats)
class DailyCampusStatsAdmin(ReadOnly):
    list_display = ["campus", "date", "signups", "posts", "views", "taps", "searches", "zero_result_searches"]
    list_filter = ["campus"]
    date_hierarchy = "date"


@admin.register(PendingEvent)
class PendingEventAdmin(ReadOnly):
    list_display = ["pk", "created_at"]
