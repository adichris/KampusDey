"""Shared unfold admin base."""

from unfold.admin import ModelAdmin, StackedInline, TabularInline


class KDModelAdmin(ModelAdmin):
    list_per_page = 50
    warn_unsaved_form = True
    compressed_fields = True


class KDTabularInline(TabularInline):
    extra = 0


class KDStackedInline(StackedInline):
    extra = 0
