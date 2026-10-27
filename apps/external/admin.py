from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.admin_base import KDModelAdmin, KDTabularInline

from .models import ExternalJob, ExternalRun, ExternalSource, Place, PlaceCampus, PlaceClaim
from .services import SourceNotRunnable, approve_source, decide_claim, run_source


class RunInline(KDTabularInline):
    model = ExternalRun
    fields = ["started_at", "finished_at", "status", "created", "updated", "removed", "error"]
    readonly_fields = fields
    can_delete = False
    max_num = 0
    ordering = ["-started_at"]


@admin.register(ExternalSource)
class ExternalSourceAdmin(KDModelAdmin):
    list_display = ["name", "kind", "permission_status", "enabled", "last_run_at", "last_status"]
    list_filter = ["kind", "permission_status", "enabled"]
    readonly_fields = ["approved_by", "approved_at", "last_run_at", "last_status"]
    inlines = [RunInline]
    actions = ["approve", "suspend", "run_now"]

    @admin.display(description=_("Terms"))
    def terms(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', obj.terms_url, obj.terms_url)

    @admin.action(description=_("Approve (requires 'I have reviewed the terms')"))
    def approve(self, request, queryset):
        for source in queryset:
            try:
                approve_source(source, request.user)
                messages.success(request, _("%(s)s approved.") % {"s": source})
            except ValueError as exc:
                messages.error(request, f"{source}: {exc}")

    @admin.action(description=_("Suspend (hides all its content now)"))
    def suspend(self, request, queryset):
        queryset.update(permission_status=ExternalSource.Permission.SUSPENDED, enabled=False)

    @admin.action(description=_("Run now (respects minimum interval)"))
    def run_now(self, request, queryset):
        for source in queryset:
            try:
                run = run_source(source)
                messages.info(request, f"{source}: {run.status} (+{run.created}/~{run.updated}/-{run.removed})")
            except SourceNotRunnable as exc:
                messages.warning(request, f"{source}: {exc}")


@admin.register(ExternalRun)
class ExternalRunAdmin(KDModelAdmin):
    list_display = ["source", "started_at", "status", "created", "updated", "removed"]
    list_filter = ["source", "status"]
    readonly_fields = ["source", "started_at", "finished_at", "status", "created", "updated", "removed", "error"]


class PlaceCampusInline(KDTabularInline):
    model = PlaceCampus
    autocomplete_fields = ["campus"]


@admin.register(Place)
class PlaceAdmin(KDModelAdmin):
    list_display = ["name", "kind", "town", "status", "owner", "osm_link", "reports_count", "last_seen_at"]
    list_filter = ["kind", "status", "external_source", "campus_links__campus"]
    search_fields = ["name", "source_id"]
    autocomplete_fields = ["town", "owner", "hostel"]
    inlines = [PlaceCampusInline]
    actions = ["hide", "unhide", "merge_into_first"]

    @admin.display(description=_("OSM"))
    def osm_link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', obj.source_url, obj.source_id) if obj.source_url else "—"

    def save_model(self, request, obj, form, change):
        if change:
            from apps.locations.signals import lock_changed_fields

            lock_changed_fields(obj, form)
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Hide"))
    def hide(self, request, queryset):
        queryset.update(status=Place.Status.HIDDEN)

    @admin.action(description=_("Unhide"))
    def unhide(self, request, queryset):
        queryset.filter(status=Place.Status.HIDDEN).update(status=Place.Status.UNCLAIMED)

    @admin.action(description=_("Merge duplicates into the first selected"))
    def merge_into_first(self, request, queryset):
        items = list(queryset.order_by("pk"))
        keep = items[0]
        for drop in items[1:]:
            for link in drop.campus_links.all():
                PlaceCampus.objects.get_or_create(place=keep, campus=link.campus, defaults={"distance_m": link.distance_m})
            drop.status = Place.Status.HIDDEN
            drop.admin_locked = True
            drop.save(update_fields=["status", "admin_locked"])
        messages.success(request, _("Merged."))


@admin.register(PlaceClaim)
class PlaceClaimAdmin(KDModelAdmin):
    list_display = ["place", "user", "proof_kind", "status", "created_at"]
    list_filter = ["status", "proof_kind"]
    readonly_fields = ["place", "user", "proof_kind", "proof", "reviewed_by", "reviewed_at"]
    actions = ["approve", "reject"]

    @admin.action(description=_("Approve (owner becomes owner; accommodation → Hostel)"))
    def approve(self, request, queryset):
        for claim in queryset.filter(status="pending"):
            decide_claim(claim, True, request.user)
        messages.success(request, _("Approved."))

    @admin.action(description=_("Reject (enter the reason on each claim first)"))
    def reject(self, request, queryset):
        for claim in queryset.filter(status="pending"):
            decide_claim(claim, False, request.user, claim.reason)
        messages.success(request, _("Rejected."))


@admin.register(ExternalJob)
class ExternalJobAdmin(KDModelAdmin):
    list_display = ["title", "company", "category", "candidate_location", "status", "published_at"]
    list_filter = ["status", "external_source", "category"]
    search_fields = ["title", "company"]
    actions = ["hide"]

    @admin.action(description=_("Hide"))
    def hide(self, request, queryset):
        queryset.update(status=ExternalJob.Status.HIDDEN)


@admin.register(PlaceCampus)
class PlaceCampusAdmin(KDModelAdmin):
    list_display = ["place", "campus", "distance_m"]
    autocomplete_fields = ["place", "campus"]
