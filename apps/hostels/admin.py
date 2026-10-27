from django.contrib import admin

from apps.core.admin_base import KDModelAdmin, KDTabularInline

from .models import Hostel, HostelPhoto, HostelRoomType
from .services import sync_room_type_listing


class RoomTypeInline(KDTabularInline):
    model = HostelRoomType
    fields = [
        "name",
        "room_type",
        "gender",
        "price",
        "price_period",
        "total_rooms",
        "available_rooms",
        "listing",
    ]
    readonly_fields = ["listing"]


class PhotoInline(KDTabularInline):
    model = HostelPhoto
    fields = ["image", "order"]


@admin.register(Hostel)
class HostelAdmin(KDModelAdmin):
    list_display = ["name", "owner", "town", "is_verified", "created_at"]
    list_filter = ["is_verified", "town__region"]
    search_fields = ["name", "owner__email"]
    autocomplete_fields = ["owner", "town", "contact_card"]
    filter_horizontal = ["campuses"]
    inlines = [RoomTypeInline, PhotoInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        for rt in form.instance.room_types.all():
            sync_room_type_listing(rt)


@admin.register(HostelRoomType)
class HostelRoomTypeAdmin(KDModelAdmin):
    list_display = ["hostel", "name", "room_type", "price", "total_rooms", "available_rooms"]
    search_fields = ["name", "hostel__name"]
    autocomplete_fields = ["hostel"]
    readonly_fields = ["listing"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        sync_room_type_listing(obj)


@admin.register(HostelPhoto)
class HostelPhotoAdmin(KDModelAdmin):
    list_display = ["hostel", "order"]
    autocomplete_fields = ["hostel"]
