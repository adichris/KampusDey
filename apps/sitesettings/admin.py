from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from apps.core.admin_base import KDModelAdmin
from apps.listings.sections import SECTIONS
from apps.locations.models import Campus

from .models import IntegrationSettings, SectionAvailability
from .services import send_test_email, send_test_sms, smtp_status, sync_google_app

SECRET_FIELDS = [
    "sms_api_key",
    "sms_api_secret",
    "turnstile_secret",
    "geolite2_license_key",
    "smtp_password",
    "s3_secret_access_key",
    "google_client_secret",
]


class IntegrationSettingsForm(forms.ModelForm):
    """Secrets are never rendered back: the admin sees '•••• set' and may type a replacement."""

    clear_secrets = forms.MultipleChoiceField(
        required=False,
        choices=[(n, n) for n in SECRET_FIELDS],
        widget=forms.CheckboxSelectMultiple,
        label=_("Clear these secrets"),
    )

    class Meta:
        model = IntegrationSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in SECRET_FIELDS:
            is_set = bool(getattr(self.instance, name, ""))
            self.fields[name] = forms.CharField(
                required=False,
                label=self.fields[name].label,
                widget=forms.PasswordInput(
                    render_value=False,
                    attrs={
                        "autocomplete": "new-password",
                        "placeholder": "•••• set" if is_set else "",
                    },
                ),
                help_text=_("•••• set — type a new value to replace, leave empty to keep")
                if is_set
                else _("Not set"),
            )

    def clean(self):
        data = super().clean()
        for name in SECRET_FIELDS:
            if not data.get(name):
                data[name] = getattr(self.instance, name, "")
            if name in (data.get("clear_secrets") or []):
                data[name] = ""
        return data


@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(KDModelAdmin):
    form = IntegrationSettingsForm
    readonly_fields = ["geolite2_last_updated"]
    fieldsets = (
        (
            _("Email (SMTP)"),
            {
                "description": _(
                    "Leave the host empty to use the EMAIL_* environment variables. "
                    "Use “Send test email” above after saving."
                ),
                "fields": (
                    "smtp_host",
                    "smtp_port",
                    "smtp_username",
                    "smtp_password",
                    "smtp_use_tls",
                    "smtp_use_ssl",
                    "email_from",
                ),
            },
        ),
        (
            _("File storage (S3 / Cloudflare R2)"),
            {
                "description": _(
                    "Leave the bucket empty to keep uploads on this server's disk. Switching "
                    "does not copy existing files; copy MEDIA_ROOT to the bucket first."
                ),
                "fields": (
                    "s3_bucket",
                    "s3_access_key_id",
                    "s3_secret_access_key",
                    "s3_endpoint_url",
                    "s3_region",
                    "s3_custom_domain",
                    "s3_private_bucket",
                ),
            },
        ),
        (
            _("Google sign-in"),
            {
                "description": _(
                    "OAuth client from Google Cloud Console. Redirect URI: "
                    "<SITE_URL>/accounts/google/login/callback/"
                ),
                "fields": ("google_client_id", "google_client_secret"),
            },
        ),
        (
            _("SMS"),
            {
                "fields": (
                    "sms_provider",
                    "sms_api_key",
                    "sms_api_secret",
                    "sms_sender_id",
                    "require_phone_verification",
                )
            },
        ),
        (_("Cloudflare Turnstile"), {"fields": ("turnstile_site_key", "turnstile_secret")}),
        (
            _("MaxMind GeoLite2"),
            {"fields": ("geolite2_account_id", "geolite2_license_key", "geolite2_last_updated")},
        ),
        (_("Umami analytics"), {"fields": ("umami_script_url", "umami_website_id")}),
        (_("Secrets"), {"fields": ("clear_secrets",)}),
    )
    change_form_template = "admin/sitesettings/integration_change_form.html"

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        sync_google_app(obj)

    def changelist_view(self, request, extra_context=None):
        obj = IntegrationSettings.load()
        return redirect(reverse("admin:sitesettings_integrationsettings_change", args=[obj.pk]))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "smtp": smtp_status()}
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        return [
            path(
                "test-email/",
                self.admin_site.admin_view(self.test_email),
                name="sitesettings_test_email",
            ),
            path(
                "test-sms/", self.admin_site.admin_view(self.test_sms), name="sitesettings_test_sms"
            ),
            path(
                "geolite2/",
                self.admin_site.admin_view(self.update_geoip),
                name="sitesettings_geolite2",
            ),
        ] + super().get_urls()

    def _back(self):
        return redirect(reverse("admin:sitesettings_integrationsettings_changelist"))

    def test_email(self, request):
        if request.method == "POST" and request.user.is_superuser:
            try:
                send_test_email(request.POST.get("to") or request.user.email)
                messages.success(request, _("Test email sent."))
            except Exception as exc:  # show SMTP errors to the admin
                messages.error(request, _("Email failed: %(e)s") % {"e": exc})
        return self._back()

    def test_sms(self, request):
        if request.method == "POST" and request.user.is_superuser:
            ok = send_test_sms(request.POST.get("to", ""))
            (messages.success if ok else messages.error)(
                request, _("Test SMS sent.") if ok else _("SMS failed.")
            )
        return self._back()

    def update_geoip(self, request):
        if request.method == "POST" and request.user.is_superuser:
            from apps.locations.geoip import update_geolite2

            try:
                update_geolite2()
                messages.success(request, _("GeoLite2 updated."))
            except Exception as exc:
                messages.error(request, str(exc))
        return self._back()


@admin.register(SectionAvailability)
class SectionAvailabilityAdmin(KDModelAdmin):
    list_display = ["section", "campus", "enabled"]
    list_filter = ["section", "enabled"]
    list_editable = ["enabled"]
    autocomplete_fields = ["campus"]

    def get_urls(self):
        return [
            path("matrix/", self.admin_site.admin_view(self.matrix), name="sitesettings_matrix")
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "matrix_url": reverse("admin:sitesettings_matrix"),
        }
        return super().changelist_view(request, extra_context)

    def matrix(self, request):
        """Per-campus matrix: rows = campuses (plus 'All campuses'), columns = sections."""
        from .services import section_enabled

        campuses = list(Campus.objects.visible().order_by("name")[:300])
        if request.method == "POST":
            for campus in [None, *campuses]:
                for slug in SECTIONS:
                    key = f"{campus.pk if campus else 'all'}:{slug}"
                    wanted = key in request.POST
                    current = section_enabled(slug, campus)
                    if campus is None:
                        SectionAvailability.objects.update_or_create(
                            section=slug, campus=None, defaults={"enabled": wanted}
                        )
                    elif (
                        wanted != current
                        or SectionAvailability.objects.filter(section=slug, campus=campus).exists()
                    ):
                        SectionAvailability.objects.update_or_create(
                            section=slug, campus=campus, defaults={"enabled": wanted}
                        )
            messages.success(request, _("Section availability saved."))
            return redirect(reverse("admin:sitesettings_matrix"))
        rows = [
            {
                "key": "all",
                "label": _("All campuses (default)"),
                "cells": [(slug, section_enabled(slug, None)) for slug in SECTIONS],
            },
        ] + [
            {
                "key": c.pk,
                "label": str(c),
                "cells": [(slug, section_enabled(slug, c)) for slug in SECTIONS],
            }
            for c in campuses
        ]
        ctx = {
            **self.admin_site.each_context(request),
            "title": _("Section availability matrix"),
            "sections": list(SECTIONS.values()),
            "rows": rows,
        }
        return render(request, "admin/sitesettings/matrix.html", ctx)
