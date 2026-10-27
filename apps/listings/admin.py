from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.core.admin_base import KDModelAdmin, KDStackedInline, KDTabularInline

from . import models as m
from .services import approve, archive, mark_taken


class PhotoInline(KDTabularInline):
    model = m.ListingPhoto
    fields = ["image", "order", "width", "height", "phash"]
    readonly_fields = ["width", "height", "phash"]


class CampusLinkInline(KDTabularInline):
    model = m.ListingCampus
    autocomplete_fields = ["campus"]


DETAIL_INLINES = []
for _model in [
    m.RoomDetails,
    m.RoommateDetails,
    m.ShortStayDetails,
    m.ItemDetails,
    m.WantedDetails,
    m.ServiceDetails,
    m.JobDetails,
    m.JobRequestDetails,
    m.ErrandDetails,
    m.FoodDetails,
    m.EventDetails,
    m.NoteDetails,
    m.StudyDetails,
    m.LostFoundDetails,
    m.TripDetails,
    m.AlertDetails,
    m.QuestionDetails,
]:
    DETAIL_INLINES.append(
        type(
            f"{_model.__name__}Inline",
            (KDStackedInline,),
            {"model": _model, "max_num": 1, "can_delete": False},
        )
    )


@admin.register(m.Listing)
class ListingAdmin(KDModelAdmin):
    list_display = [
        "title",
        "section",
        "owner",
        "town",
        "status",
        "is_hidden",
        "score",
        "reports_count",
        "published_at",
    ]
    list_filter = ["status", "section", "is_hidden", "seller_type", "town__region"]
    search_fields = ["title", "description", "owner__email", "slug"]
    autocomplete_fields = ["owner", "town", "area", "contact_card"]
    readonly_fields = [
        "score",
        "views_7d",
        "taps_7d",
        "likes_7d",
        "likes_count",
        "comments_count",
        "reports_count",
        "published_at",
        "approved_at",
        "confirmed_at",
        "status_changed_at",
        "created_at",
    ]
    list_select_related = ["owner", "town"]
    actions = ["approve_selected", "hide_selected", "mark_taken_selected", "archive_selected"]
    date_hierarchy = "created_at"

    def get_inlines(self, request, obj):
        if obj is None:
            return [PhotoInline, CampusLinkInline]
        section_model = obj.section_obj.model
        return [PhotoInline, CampusLinkInline] + [
            i for i in DETAIL_INLINES if i.model is section_model
        ]

    @admin.action(description=_("Approve"))
    def approve_selected(self, request, queryset):
        for listing in queryset:
            approve(listing)
        messages.success(request, _("Approved."))

    @admin.action(description=_("Hide pending review"))
    def hide_selected(self, request, queryset):
        queryset.update(is_hidden=True, hidden_reason="hidden by staff")

    @admin.action(description=_("Mark taken"))
    def mark_taken_selected(self, request, queryset):
        for listing in queryset:
            mark_taken(listing)

    @admin.action(description=_("Archive (delete photos)"))
    def archive_selected(self, request, queryset):
        for listing in queryset:
            archive(listing)


class CategoryAdmin(KDModelAdmin):
    list_display = ["name", "slug", "icon", "min_price", "max_price", "order", "is_active"]
    list_editable = ["min_price", "max_price", "order", "is_active"]
    prepopulated_fields = {"slug": ["name"]}
    search_fields = ["name"]


admin.site.register(m.ItemCategory, CategoryAdmin)
admin.site.register(m.ServiceCategory, CategoryAdmin)


@admin.register(m.ListingPhoto)
class ListingPhotoAdmin(KDModelAdmin):
    list_display = ["listing", "order", "width", "height", "phash"]
    search_fields = ["listing__title", "phash"]
    autocomplete_fields = ["listing"]


@admin.register(m.ListingCampus)
class ListingCampusAdmin(KDModelAdmin):
    list_display = ["listing", "campus", "distance_m", "is_manual", "is_excluded"]
    list_filter = ["is_manual", "is_excluded"]
    autocomplete_fields = ["listing", "campus"]
