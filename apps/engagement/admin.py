from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.admin_base import KDModelAdmin

from .models import Comment, Like, Report, Review, SavedSearch


@admin.register(Like)
class LikeAdmin(KDModelAdmin):
    list_display = ["user", "listing", "created_at"]
    autocomplete_fields = ["user", "listing"]


@admin.register(Comment)
class CommentAdmin(KDModelAdmin):
    list_display = ["body", "listing", "author", "is_owner_reply", "is_hidden", "created_at"]
    list_filter = ["is_hidden", "is_owner_reply"]
    search_fields = ["body", "author__email"]
    autocomplete_fields = ["listing", "author", "parent"]


@admin.register(Review)
class ReviewAdmin(KDModelAdmin):
    list_display = ["reviewer", "hostel", "target_user", "rating", "status", "created_at"]
    list_filter = ["status", "rating"]
    autocomplete_fields = ["reviewer", "hostel", "target_user"]


@admin.register(Report)
class ReportAdmin(KDModelAdmin):
    list_display = ["target_link", "reason", "reporter", "status", "created_at"]
    list_filter = ["status", "reason", "content_type"]
    search_fields = ["details", "reporter__email"]
    readonly_fields = [
        "content_type",
        "object_id",
        "reporter",
        "reason",
        "details",
        "conversation_messages",
    ]
    actions = ["mark_actioned", "dismiss"]

    @admin.display(description=_("Target"))
    def target_link(self, obj):
        target = obj.target
        if target is None:
            return "—"
        url = reverse(
            f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
            args=[obj.object_id],
        )
        return format_html('<a href="{}">{}</a>', url, str(target)[:60])

    @admin.display(description=_("Conversation (reported)"))
    def conversation_messages(self, obj):
        """Admins can read a conversation only through a report (§6.8)."""
        if obj.content_type.model != "conversation" or obj.target is None:
            return "—"
        rows = [
            format_html(
                "<p><b>{}</b>: {}</p>",
                obj.target.alias_for(m.sender) if m.sender else "system",
                m.body,
            )
            for m in obj.target.messages.order_by("created_at")[:200]
        ]
        return format_html("".join(str(r) for r in rows)) if rows else "—"

    def save_model(self, request, obj, form, change):
        obj.handled_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Mark actioned"))
    def mark_actioned(self, request, queryset):
        queryset.update(status=Report.Status.ACTIONED, handled_by=request.user)
        messages.success(request, _("Updated."))

    @admin.action(description=_("Dismiss"))
    def dismiss(self, request, queryset):
        from apps.listings.models import Listing

        for report in queryset:
            report.status = Report.Status.DISMISSED
            report.handled_by = request.user
            report.save()
            target = report.target
            if isinstance(target, Listing):
                open_count = Report.objects.filter(
                    content_type=report.content_type, object_id=report.object_id, status="open"
                ).count()
                Listing.objects.filter(pk=target.pk).update(reports_count=open_count)
        messages.success(request, _("Dismissed."))


@admin.register(SavedSearch)
class SavedSearchAdmin(KDModelAdmin):
    list_display = ["user", "section", "campus", "town", "is_active", "last_notified_at"]
    list_filter = ["section", "is_active"]
    autocomplete_fields = ["user", "campus", "town"]
