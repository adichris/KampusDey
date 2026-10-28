"""django-unfold admin configuration: grouped sidebar and dashboard (§6.14)."""

from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


def _cl(app_model: str):
    app, model = app_model.split(".")
    return reverse_lazy(f"admin:{app}_{model}_changelist")


def _item(title, icon, app_model, badge=None, permission=None):
    item = {"title": title, "icon": icon, "link": _cl(app_model)}
    if badge:
        item["badge"] = badge
    if permission:
        item["permission"] = permission
    return item


B = "apps.dashboard.admin_dashboard."

UNFOLD = {
    "SITE_TITLE": "KampusDey admin",
    "SITE_HEADER": "KampusDey",
    "SITE_SYMBOL": "school",
    "SITE_FAVICONS": [
        {"rel": "icon", "type": "image/svg+xml", "href": lambda r: static("img/icon.svg")}
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "DASHBOARD_CALLBACK": B + "dashboard_callback",
    "COLORS": {
        "primary": {
            "50": "236 253 245",
            "100": "209 250 229",
            "200": "167 243 208",
            "300": "110 231 183",
            "400": "52 211 153",
            "500": "14 124 102",
            "600": "13 110 91",
            "700": "11 94 78",
            "800": "9 77 64",
            "900": "6 60 50",
            "950": "4 40 33",
        }
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Overview"),
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": _("Listings"),
                "collapsible": True,
                "items": [
                    _item(_("Listings"), "list_alt", "listings.listing"),
                    _item(_("Item categories"), "category", "listings.itemcategory"),
                    _item(_("Service categories"), "handyman", "listings.servicecategory"),
                    _item(_("Boosts"), "rocket_launch", "boosts.boost"),
                ],
            },
            {
                "title": _("Hostels"),
                "collapsible": True,
                "items": [
                    _item(_("Hostels"), "apartment", "hostels.hostel"),
                    _item(_("Room types"), "bed", "hostels.hostelroomtype"),
                ],
            },
            {
                "title": _("Locations"),
                "collapsible": True,
                "items": [
                    _item(_("Regions"), "map", "locations.region"),
                    _item(_("Districts"), "map", "locations.district"),
                    _item(_("Towns"), "location_city", "locations.town"),
                    _item(_("Institutions"), "account_balance", "locations.institution"),
                    _item(
                        _("Campuses"), "school", "locations.campus", B + "badge_unverified_campuses"
                    ),
                    _item(_("Areas"), "pin_drop", "locations.area"),
                    _item(
                        _("Campus requests"),
                        "add_location",
                        "locations.campusrequest",
                        B + "badge_campus_requests",
                    ),
                    _item(_("Source records"), "database", "locations.sourcerecord"),
                ],
            },
            {
                "title": _("Users"),
                "collapsible": True,
                "items": [
                    _item(_("Users"), "person", "accounts.user"),
                    _item(_("Profiles"), "badge", "accounts.profile"),
                    _item(
                        _("Verification requests"),
                        "verified",
                        "accounts.verificationrequest",
                        B + "badge_verifications",
                    ),
                ],
            },
            {
                "title": _("Moderation"),
                "collapsible": True,
                "items": [
                    _item(
                        _("Moderation queue"),
                        "gavel",
                        "moderation.moderationitem",
                        B + "badge_moderation",
                    ),
                    _item(_("Reports"), "flag", "engagement.report", B + "badge_reports"),
                    _item(_("Banned terms"), "block", "moderation.bannedterm"),
                    _item(_("Scam alerts"), "warning", "moderation.scamalert"),
                    _item(_("Price suggestions"), "price_check", "moderation.pricerangesuggestion"),
                ],
            },
            {
                "title": _("Engagement"),
                "collapsible": True,
                "items": [
                    _item(_("Comments"), "chat_bubble", "engagement.comment"),
                    _item(_("Reviews"), "star", "engagement.review"),
                    _item(_("Saved searches"), "notifications_active", "engagement.savedsearch"),
                    _item(_("Conversations"), "forum", "chat.conversation"),
                ],
            },
            {
                "title": _("External content"),
                "collapsible": True,
                "items": [
                    _item(_("Source registry"), "hub", "external.externalsource"),
                    _item(_("Runs"), "history", "external.externalrun"),
                    _item(_("Places"), "storefront", "external.place"),
                    _item(
                        _("Place claims"), "how_to_reg", "external.placeclaim", B + "badge_claims"
                    ),
                    _item(_("Remote jobs"), "work", "external.externaljob"),
                ],
            },
            {
                "title": _("Telemetry"),
                "collapsible": True,
                "items": [
                    _item(_("Daily listing stats"), "monitoring", "telemetry.dailylistingstats"),
                    _item(_("Daily campus stats"), "insights", "telemetry.dailycampusstats"),
                    _item(_("Raw events"), "bolt", "telemetry.event"),
                ],
            },
            {
                "title": _("Growth"),
                "collapsible": True,
                "items": [
                    _item(_("Referrals"), "group_add", "growth.referral"),
                    _item(_("Spotlights"), "star_rate", "growth.spotlight"),
                ],
            },
            {
                "title": _("Settings"),
                "collapsible": True,
                "items": [
                    {
                        "title": _("Settings overview"),
                        "icon": "dashboard_customize",
                        "link": reverse_lazy("settings_overview"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Site settings"),
                        "icon": "tune",
                        "link": reverse_lazy("admin:constance_config_changelist"),
                    },
                    _item(
                        _("Section availability"), "toggle_on", "sitesettings.sectionavailability"
                    ),
                    {
                        "title": _("Integrations"),
                        "icon": "key",
                        "link": reverse_lazy("admin:sitesettings_integrationsettings_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    _item(_("Feature flags"), "flag_circle", "waffle.flag"),
                ],
            },
        ],
    },
}
