from django.contrib import admin

from apps.core.admin_base import KDModelAdmin

from .models import Block, Conversation


@admin.register(Conversation)
class ConversationAdmin(KDModelAdmin):
    """Metadata only. Message bodies are readable only through a report (see Reports)."""

    list_display = ["listing", "starter_alias", "owner_alias", "last_message_at", "is_blocked"]
    list_filter = ["is_blocked"]
    search_fields = ["listing__title", "starter_alias", "owner_alias"]
    readonly_fields = [
        "listing",
        "starter",
        "owner",
        "starter_alias",
        "owner_alias",
        "last_message_at",
    ]

    def has_add_permission(self, request):
        return False


@admin.register(Block)
class BlockAdmin(KDModelAdmin):
    list_display = ["blocker", "blocked", "created_at"]
    autocomplete_fields = ["blocker", "blocked"]
