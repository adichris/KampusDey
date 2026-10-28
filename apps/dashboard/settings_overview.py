"""Admin page: every major setting at a glance, with what is active and where to change it."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext as _


def _card(title, icon, rows, edit_url="", edit_label="", status="ok", note=""):
    return {
        "title": title,
        "icon": icon,
        "rows": rows,
        "edit_url": edit_url,
        "edit_label": edit_label or _("Change"),
        "status": status,  # ok | warn | off
        "note": note,
    }


def overview(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    from constance import config

    from apps.sitesettings.models import IntegrationSettings
    from apps.sitesettings.services import (
        google_status,
        runtime_status,
        smtp_status,
        storage_status,
    )

    integ = IntegrationSettings.get_cached()
    integrations = reverse("admin:sitesettings_integrationsettings_changelist")
    yes, no = _("Yes"), _("No")
    storage, email, google, run = storage_status(), smtp_status(), google_status(), runtime_status()

    cards = [
        _card(
            _("File storage"),
            "cloud_upload",
            [
                (
                    _("Public uploads"),
                    _("S3 bucket “%s”") % storage["bucket"]
                    if storage["public"] == "s3"
                    else _("This server's disk"),
                ),
                (
                    _("Configured in"),
                    {"admin": _("Admin"), "env": _("Environment")}.get(storage["source"], "—"),
                ),
                (
                    _("Private documents"),
                    _("Private S3 bucket")
                    if storage["private"] == "s3"
                    else _("This server's disk (never public)"),
                ),
                (_("Media folder"), storage["media_root"]),
                (_("Served by Django"), yes if storage["serve_media"] else no),
            ],
            integrations + "#file-storage-s3-cloudflare-r2",
            note=_("Uploads stay on this server until an S3 bucket is set.")
            if storage["public"] == "local"
            else "",
        ),
        _card(
            _("Email"),
            "mail",
            [
                (_("Sending with"), email["backend"]),
                (
                    _("Configured in"),
                    _("Admin") if email["source"] == "admin" else _("Environment"),
                ),
                (_("Server"), f"{email['host']}:{email['port']}"),
                (_("From"), email["from"]),
            ],
            integrations,
            status="ok" if email["source"] == "admin" or email.get("sends_real_mail") else "warn",
            note=""
            if email["source"] == "admin" or email.get("sends_real_mail")
            else _("Emails are only printed to the log. Set SMTP to send real email."),
        ),
        _card(
            _("Sign-in & security"),
            "shield_lock",
            [
                (_("Google sign-in"), yes if google["enabled"] else no),
                (_("Bot check (Turnstile)"), yes if integ.turnstile_secret else no),
                (_("Phone verification required"), yes if integ.require_phone_verification else no),
                (_("Staff two-factor required"), yes if run["staff_mfa"] else no),
            ],
            integrations,
            status="ok" if run["staff_mfa"] else "warn",
        ),
        _card(
            _("SMS"),
            "sms",
            [
                (_("Provider"), integ.get_sms_provider_display()),
                (_("Sender ID"), integ.sms_sender_id or "—"),
            ],
            integrations,
            status="ok" if integ.sms_provider not in ("none", "console") else "off",
        ),
        _card(
            _("Marketplace rules"),
            "tune",
            [
                (_("Listings expire after (days)"), config.EXPIRY_EXPIRE_DAYS),
                (_("Free boosts per week"), config.BOOSTS_PER_WEEK),
                (_("Guest chat messages before sign-up"), config.GUEST_CHAT_MESSAGE_LIMIT),
                (_("Max photos per listing"), config.MAX_PHOTOS),
                (_("Themes offered"), config.THEMES_OFFERED),
            ],
            reverse("admin:constance_config_changelist"),
            _("Open site settings"),
        ),
        _card(
            _("Sections & features"),
            "toggle_on",
            [
                (_("Sections per campus"), _("Turn sections on or off")),
                (_("Feature flags"), _("Gradual roll-outs")),
            ],
            reverse("admin:sitesettings_sectionavailability_changelist"),
            _("Section availability"),
        ),
        _card(
            _("Maps, places & analytics"),
            "map",
            [
                (_("Map tiles"), config.MAP_TILE_URL),
                (_("GeoLite2 (IP location)"), yes if integ.geolite2_license_key else no),
                (_("Umami analytics"), yes if integ.umami_website_id else no),
            ],
            integrations,
        ),
        _card(
            _("Server"),
            "dns",
            [
                (_("Site address"), run["site_url"]),
                (_("Database"), run["database"]),
                (_("Redis"), yes if run["redis"] else _("No (background jobs run inline)")),
                (_("Error tracking (Sentry)"), yes if run["sentry"] else no),
                (_("Debug mode"), _("ON, turn off in production") if run["debug"] else _("Off")),
            ],
            status="warn" if run["debug"] else "ok",
            note=_("These come from environment variables (.env) and need a restart to change."),
        ),
    ]
    context = {
        **admin.site.each_context(request),
        "title": _("Settings overview"),
        "cards": cards,
    }
    return TemplateResponse(request, "admin/settings_overview.html", context)
