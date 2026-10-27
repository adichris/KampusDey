from django.contrib import admin, messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.admin_base import KDModelAdmin, KDTabularInline

from .importers.pipeline import merge_campuses, merge_institutions, possible_duplicates
from .models import Area, Campus, CampusRequest, District, ImportLog, Institution, Region, ReviewStatus, SourceRecord, Town
from .services import approve_campus_request, reject_campus_request
from .signals import lock_changed_fields

PROVENANCE = (
    _("Provenance"),
    {"fields": ("source", "source_id", "source_url", "retrieved_at", "licence", "confidence", "review_status",
                "admin_locked", "locked_fields")},
)


class LockingAdmin(KDModelAdmin):
    """Admin edits lock the changed fields so imports never overwrite them."""

    readonly_fields = ["retrieved_at"]
    actions = ["verify", "reject"]

    def save_model(self, request, obj, form, change):
        if change:
            lock_changed_fields(obj, form)
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Verify"))
    def verify(self, request, queryset):
        n = queryset.update(review_status=ReviewStatus.VERIFIED)
        messages.success(request, _("%(n)s verified.") % {"n": n})

    @admin.action(description=_("Reject (hide from users)"))
    def reject(self, request, queryset):
        n = queryset.update(review_status=ReviewStatus.REJECTED)
        messages.success(request, _("%(n)s rejected.") % {"n": n})

    @admin.display(description=_("Source"))
    def source_link(self, obj):
        if obj.source_url:
            return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', obj.source_url, obj.get_source_display())
        return obj.get_source_display()

    @admin.display(description=_("Map"))
    def mini_map(self, obj):
        if getattr(obj, "lat", None) is None:
            return "—"
        lat, lng = f"{obj.lat:.5f}", f"{obj.lng:.5f}"
        return format_html(
            '<a href="https://www.openstreetmap.org/?mlat={0}&mlon={1}#map=16/{0}/{1}" target="_blank" rel="noopener">'
            "{0}, {1} ↗</a>",
            lat, lng,
        )


@admin.register(Region)
class RegionAdmin(LockingAdmin):
    list_display = ["name", "hdx_pcode", "has_boundary", "review_status"]
    search_fields = ["name"]
    exclude = ["boundary"]

    @admin.display(boolean=True, description=_("Boundary"))
    def has_boundary(self, obj):
        return bool(obj.boundary)


@admin.register(District)
class DistrictAdmin(LockingAdmin):
    list_display = ["name", "region", "hdx_pcode"]
    list_filter = ["region"]
    search_fields = ["name"]
    exclude = ["boundary"]


@admin.register(Town)
class TownAdmin(LockingAdmin):
    list_display = ["name", "region", "district", "mini_map", "source_link", "review_status"]
    list_filter = ["region", "source", "review_status"]
    search_fields = ["name"]
    autocomplete_fields = ["region", "district"]


class CampusInline(KDTabularInline):
    model = Campus
    fields = ["name", "short_name", "town", "kind", "is_active", "review_status"]
    autocomplete_fields = ["town"]
    show_change_link = True


@admin.register(Institution)
class InstitutionAdmin(LockingAdmin):
    list_display = ["name", "short_name", "kind", "gtec_status", "source_link", "confidence", "review_status"]
    list_filter = ["review_status", "gtec_status", "kind", "source"]
    search_fields = ["name", "short_name", "wikidata_id"]
    inlines = [CampusInline]
    actions = ["verify", "reject", "merge_into_first"]

    @admin.action(description=_("Merge into… (keep the oldest selected, move its campuses)"))
    def merge_into_first(self, request, queryset):
        items = list(queryset.order_by("pk"))
        if len(items) < 2:
            messages.error(request, _("Select at least two."))
            return
        keep = items[0]
        for drop in items[1:]:
            merge_institutions(keep, drop)
        messages.success(request, _("Merged into %(name)s.") % {"name": keep.name})


@admin.register(Campus)
class CampusAdmin(LockingAdmin):
    list_display = ["name", "short_name", "town", "kind", "mini_map", "source_link", "confidence", "review_status", "is_active"]
    list_filter = ["review_status", "kind", "is_active", "source", "town__region"]
    search_fields = ["name", "short_name", "town__name"]
    autocomplete_fields = ["institution", "town"]
    readonly_fields = ["retrieved_at", "mini_map"]
    actions = ["verify", "reject", "merge_into_first"]
    fieldsets = (
        (None, {"fields": ("institution", "name", "short_name", "slug", "kind", "town", "is_active")}),
        (_("Location"), {"fields": ("lat", "lng", "mini_map", "osm_id")}),
        PROVENANCE,
    )

    def get_urls(self):
        return [
            path("review-queue/", self.admin_site.admin_view(self.review_queue), name="locations_review_queue"),
            path("duplicates/", self.admin_site.admin_view(self.duplicates_view), name="locations_duplicates"),
        ] + super().get_urls()

    def review_queue(self, request):
        ctx = {
            **self.admin_site.each_context(request),
            "title": _("Locations review queue"),
            "institutions": Institution.objects.filter(review_status=ReviewStatus.UNVERIFIED)[:200],
            "campuses": Campus.objects.filter(review_status=ReviewStatus.UNVERIFIED).select_related("town")[:200],
            "areas": Area.objects.filter(review_status=ReviewStatus.UNVERIFIED).select_related("campus")[:200],
            "flagged": Institution.objects.filter(gtec_status__in=["expired", "unaccredited"]),
        }
        return render(request, "admin/locations/review_queue.html", ctx)

    def duplicates_view(self, request):
        if request.method == "POST":
            keep = Campus.objects.get(pk=request.POST["keep"])
            drop = Campus.objects.get(pk=request.POST["drop"])
            merge_campuses(keep, drop)
            messages.success(request, _("Merged."))
            return redirect(reverse("admin:locations_duplicates"))
        ctx = {**self.admin_site.each_context(request), "title": _("Possible duplicate campuses"),
               "pairs": possible_duplicates()[:100]}
        return render(request, "admin/locations/duplicates.html", ctx)

    @admin.action(description=_("Merge into… (keep the oldest selected; moves areas and listings)"))
    def merge_into_first(self, request, queryset):
        items = list(queryset.order_by("pk"))
        if len(items) < 2:
            messages.error(request, _("Select at least two."))
            return
        keep = items[0]
        for drop in items[1:]:
            merge_campuses(keep, drop)
        messages.success(request, _("Merged into %(name)s.") % {"name": keep.name})


@admin.register(Area)
class AreaAdmin(LockingAdmin):
    list_display = ["name", "town", "campus", "mini_map", "source_link", "review_status"]
    list_filter = ["review_status", "source", "town__region"]
    search_fields = ["name", "town__name", "campus__name"]
    autocomplete_fields = ["town", "campus"]
    exclude = ["boundary"]


@admin.register(CampusRequest)
class CampusRequestAdmin(KDModelAdmin):
    list_display = ["name", "town_name", "region", "requester", "email", "status", "created_at"]
    list_filter = ["status", "region"]
    search_fields = ["name", "town_name"]
    actions = ["approve_and_create", "reject"]

    @admin.action(description=_("Approve and create campus"))
    def approve_and_create(self, request, queryset):
        for req in queryset.filter(status="pending"):
            approve_campus_request(req)
        messages.success(request, _("Campuses created."))

    @admin.action(description=_("Reject"))
    def reject(self, request, queryset):
        for req in queryset.filter(status="pending"):
            reject_campus_request(req)


@admin.register(SourceRecord)
class SourceRecordAdmin(KDModelAdmin):
    list_display = ["source", "kind", "source_id", "match_method", "match_score", "retrieved_at"]
    list_filter = ["source", "kind", "match_method"]
    search_fields = ["source_id"]
    readonly_fields = [f.name for f in SourceRecord._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ImportLog)
class ImportLogAdmin(KDModelAdmin):
    list_display = ["command", "source", "ok", "created_at"]
    readonly_fields = ["command", "source", "summary", "ok"]


__all__ = ["Q"]
