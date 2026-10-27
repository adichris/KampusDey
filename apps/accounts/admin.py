from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.core.admin_base import KDModelAdmin, KDStackedInline

from .models import PhoneOTP, Profile, User, VerificationRequest
from .services import decide_verification

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(ModelAdmin):
    search_fields = ["name"]


class KDUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


class KDUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class ProfileInline(KDStackedInline):
    model = Profile
    can_delete = False
    fk_name = "user"
    filter_horizontal = ["followed_campuses"]
    autocomplete_fields = ["home_campus", "home_town"]


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = KDUserChangeForm
    add_form = KDUserCreationForm
    change_password_form = AdminPasswordChangeForm
    ordering = ["-date_joined"]
    list_display = [
        "email",
        "display_name",
        "phone_verified",
        "is_staff",
        "is_active",
        "date_joined",
    ]
    list_filter = ["is_staff", "is_active", "phone_verified", "is_anonymised"]
    search_fields = ["email", "display_name", "phone"]
    readonly_fields = ["date_joined", "last_login", "alias_number"]
    inlines = [ProfileInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Profile"),
            {
                "fields": (
                    "display_name",
                    "phone",
                    "phone_verified",
                    "theme",
                    "alias_number",
                    "onboarded",
                )
            },
        ),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


@admin.register(Profile)
class ProfileAdmin(KDModelAdmin):
    list_display = [
        "user",
        "role",
        "seller_type",
        "home_campus",
        "is_ambassador",
        "verified_student",
        "verified_landlord",
    ]
    list_filter = [
        "role",
        "seller_type",
        "is_ambassador",
        "verified_student",
        "verified_landlord",
        "verified_agent",
    ]
    search_fields = ["user__email", "user__display_name", "referral_code"]
    autocomplete_fields = ["user", "home_campus", "home_town"]
    filter_horizontal = ["followed_campuses"]


@admin.register(VerificationRequest)
class VerificationRequestAdmin(KDModelAdmin):
    list_display = ["user", "kind", "status", "created_at", "reviewed_by", "reviewed_at"]
    list_filter = ["status", "kind"]
    search_fields = ["user__email"]
    readonly_fields = ["user", "kind", "document", "reviewed_by", "reviewed_at"]
    actions = ["approve", "reject"]

    @admin.action(description=_("Approve (set badge, delete document)"))
    def approve(self, request, queryset):
        for item in queryset.filter(status="pending"):
            decide_verification(item, True, request.user)
        messages.success(request, _("Approved and documents deleted."))

    @admin.action(description=_("Reject (delete document)"))
    def reject(self, request, queryset):
        for item in queryset.filter(status="pending"):
            decide_verification(item, False, request.user)
        messages.success(request, _("Rejected and documents deleted."))


@admin.register(PhoneOTP)
class PhoneOTPAdmin(KDModelAdmin):
    list_display = ["user", "phone", "created_at", "expires_at", "attempts", "used_at"]
    readonly_fields = ["user", "phone", "code_hash", "expires_at", "attempts", "used_at"]
    search_fields = ["user__email"]

    def has_add_permission(self, request):
        return False
