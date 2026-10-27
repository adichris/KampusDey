from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.admin_base import KDModelAdmin

from .models import BannedTerm, ModerationItem, PriceRangeSuggestion, ScamAlert
from .services import decide


@admin.register(BannedTerm)
class BannedTermAdmin(KDModelAdmin):
    list_display = ["term", "is_regex", "action", "applies_to", "is_active"]
    list_filter = ["action", "applies_to", "is_active"]
    list_editable = ["action", "applies_to", "is_active"]
    search_fields = ["term"]


@admin.register(ModerationItem)
class ModerationItemAdmin(KDModelAdmin):
    list_display = ["target_link", "reason", "auto", "status", "created_at"]
    list_filter = ["status", "auto", "content_type"]
    readonly_fields = ["content_type", "object_id", "reason", "auto", "reviewed_by", "reviewed_at"]
    actions = ["approve", "reject"]

    @admin.display(description=_("Item"))
    def target_link(self, obj):
        target = obj.target
        if target is None:
            return "—"
        url = reverse(f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change", args=[obj.object_id])
        return format_html('<a href="{}">{}</a>', url, str(target)[:60])

    @admin.action(description=_("Approve selected"))
    def approve(self, request, queryset):
        for item in queryset.filter(status="pending"):
            decide(item, True, request.user)
        messages.success(request, _("Approved."))

    @admin.action(description=_("Reject selected"))
    def reject(self, request, queryset):
        for item in queryset.filter(status="pending"):
            decide(item, False, request.user)
        messages.success(request, _("Rejected."))


@admin.register(ScamAlert)
class ScamAlertAdmin(KDModelAdmin):
    list_display = ["name", "phone_last4", "confirmed_at", "is_published"]
    list_filter = ["is_published"]
    search_fields = ["name", "phone_last4"]
    actions = ["confirm_and_publish", "unpublish"]

    @admin.action(description=_("Confirm and publish"))
    def confirm_and_publish(self, request, queryset):
        queryset.update(confirmed_at=timezone.now(), is_published=True)

    @admin.action(description=_("Unpublish"))
    def unpublish(self, request, queryset):
        queryset.update(is_published=False)


@admin.register(PriceRangeSuggestion)
class PriceRangeSuggestionAdmin(KDModelAdmin):
    list_display = ["category_name", "category_kind", "suggested_min", "suggested_max", "samples", "accepted", "created_at"]
    list_filter = ["category_kind", "accepted"]
    actions = ["accept"]

    @admin.action(description=_("Accept (copy to the category)"))
    def accept(self, request, queryset):
        from apps.listings.models import ItemCategory, ServiceCategory

        for s in queryset.filter(accepted=False):
            model = ItemCategory if s.category_kind == "item" else ServiceCategory
            model.objects.filter(pk=s.category_id).update(min_price=s.suggested_min, max_price=s.suggested_max)
            s.accepted = True
            s.save(update_fields=["accepted"])
        messages.success(request, _("Accepted."))
