from django.contrib import admin

from apps.core.admin_base import KDModelAdmin, KDTabularInline

from .models import ContactCard, ContactChannel


class ChannelInline(KDTabularInline):
    model = ContactChannel


@admin.register(ContactCard)
class ContactCardAdmin(KDModelAdmin):
    list_display = ["label", "owner", "is_default", "preferred_time"]
    search_fields = ["label", "owner__email"]
    autocomplete_fields = ["owner"]
    inlines = [ChannelInline]


@admin.register(ContactChannel)
class ContactChannelAdmin(KDModelAdmin):
    list_display = ["card", "kind", "is_verified", "order"]
    list_filter = ["kind", "is_verified"]
    autocomplete_fields = ["card"]
