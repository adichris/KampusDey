from django.contrib import admin

from apps.core.admin_base import KDModelAdmin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(KDModelAdmin):
    list_display = ["recipient", "trigger", "title", "read_at", "emailed_at", "created_at"]
    list_filter = ["trigger"]
    search_fields = ["recipient__email", "title"]
    autocomplete_fields = ["recipient"]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(KDModelAdmin):
    list_display = ["user", "weekly_digest", "push_enabled"]
    autocomplete_fields = ["user"]
