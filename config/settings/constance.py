"""django-constance settings: every value an admin can change without a deploy (§6.14)."""

from django.utils.translation import gettext_lazy as _

CONSTANCE_ADDITIONAL_FIELDS = {
    "json": ["django.forms.fields.JSONField", {"required": False}],
    "long_text": [
        "django.forms.fields.CharField",
        {"widget": "django.forms.Textarea", "required": False},
    ],
}

CONSTANCE_CONFIG = {
    # Lifecycle
    "EXPIRY_NEEDS_CHECK_DAYS": (14, _("Days before a listing is asked 'Still available?'"), int),
    "EXPIRY_EXPIRE_DAYS": (30, _("Days before a listing expires"), int),
    "EXPIRY_ARCHIVE_DAYS": (90, _("Days before a listing is archived and photos deleted"), int),
    "SECTION_EXPIRY_OVERRIDES": (
        {},
        _('Per-section overrides, e.g. {"rooms": {"needs_check": 21, "expire": 45}}'),
        "json",
    ),
    "FOOD_POST_MAX_HOURS": (6, _("Maximum hours a food post stays up"), int),
    # Boosts
    "BOOSTS_PER_WEEK": (2, _("Free boosts per user per rolling 7 days"), int),
    "BOOST_DURATION_DAYS": (3, _("How long a boost lasts"), int),
    "BOOST_SLOTS_PER_PAGE": (4, _("Maximum boosted listings per page"), int),
    "BOOST_MIN_ACCOUNT_AGE_HOURS": (24, _("Minimum account age to boost"), int),
    # Ranking
    "W_FRESH": (1.0, _("Ranking weight: freshness"), float),
    "W_ACT": (1.0, _("Ranking weight: activity"), float),
    "W_QUAL": (0.3, _("Ranking weight: quality"), float),
    "W_REPORT": (0.5, _("Ranking weight: reports penalty"), float),
    "ACTIVITY_CAP": (3.0, _("Cap on the activity term"), float),
    "FRESH_HALF_LIFE_DAYS": (7.0, _("Freshness decay constant in days"), float),
    # Maps & location
    "NEARBY_RADII": ("500,1000,2000", _("Radius rings on the Nearby map (metres)"), str),
    "CAMPUS_AUTOLINK_RADIUS_M": (3000, _("Auto-link listings to campuses within (m)"), int),
    "LOCATION_SNAP_M": (200, _("Snap listing locations to a grid of (m)"), int),
    "WALKING_M_PER_MIN": (80, _("Walking speed for 'minutes away' (m/min)"), int),
    "MAP_TILE_URL": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", _("Map tile URL"), str),
    "MAP_ATTRIBUTION": (
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        _("Map attribution (HTML)"),
        str,
    ),
    # Moderation & trust
    "NEW_SELLER_REVIEW_COUNT": (3, _("Posts reviewed until a seller has this many approved"), int),
    "REPORTS_AUTO_HIDE": (3, _("Open reports that auto-hide a listing"), int),
    "FIRST_CONTACT_MIN_ACCOUNT_AGE_HOURS": (24, _("Account age to message someone new"), int),
    "CHAT_NEW_ACCOUNT_DAYS": (3, _("Days an account counts as new for chat limits"), int),
    "CHAT_NEW_ACCOUNT_DAILY_LIMIT": (20, _("Messages per day for new accounts"), int),
    "GUEST_CHAT_MESSAGE_LIMIT": (
        10,
        _("Messages a guest can send in one chat before they must sign up"),
        int,
    ),
    "MAX_PHOTOS": (8, _("Maximum photos per listing"), int),
    "MAX_UPLOAD_MB": (8, _("Maximum upload size per photo (MB)"), int),
    # Appearance
    "THEMES_OFFERED": (
        "system,kampusdey,kampusdey-dark,cupcake,emerald,corporate,garden,lofi,retro,nord,"
        "night,coffee,dracula,sunset",
        _("Themes users can choose (comma separated)"),
        str,
    ),
    # Telemetry & growth
    "TELEMETRY_RAW_RETENTION_DAYS": (90, _("Days raw telemetry events are kept"), int),
    "AMBASSADOR_BONUS_BOOSTS": (2, _("Extra boosts per successful referral"), int),
    "RENT_CHECK_MIN_SAMPLES": (5, _("Minimum samples before rent check shows a figure"), int),
    # External content (M9.5)
    "CAMPUS_PLACES_RADIUS_M": (2000, _("Radius for places around campus (m)"), int),
    "PLACES_REFRESH_DAYS": (30, _("Days between OpenStreetMap place refreshes"), int),
    "IMPORT_PLACE_PHONES": (False, _("Import phone numbers of OSM places"), bool),
    "PLACE_REPORTS_AUTO_HIDE": (3, _("Reports that hide a place pending review"), int),
    "REMOTIVE_FETCHES_PER_DAY": (2, _("Remotive fetches per day (hard maximum 4)"), int),
    "REMOTIVE_LOCATION_KEYWORDS": (
        "worldwide,anywhere,africa,ghana,emea",
        _("Keep remote jobs whose location contains one of"),
        str,
    ),
    "REMOTIVE_CATEGORIES": (
        "customer-support,writing,design,software-dev,data,marketing,sales",
        _("Remotive category slugs to keep"),
        str,
    ),
    "EXTERNAL_JOB_MAX_AGE_DAYS": (30, _("Remote jobs older than this expire"), int),
}

CONSTANCE_CONFIG_FIELDSETS = {
    "Lifecycle": (
        "EXPIRY_NEEDS_CHECK_DAYS",
        "EXPIRY_EXPIRE_DAYS",
        "EXPIRY_ARCHIVE_DAYS",
        "SECTION_EXPIRY_OVERRIDES",
        "FOOD_POST_MAX_HOURS",
    ),
    "Boosts": (
        "BOOSTS_PER_WEEK",
        "BOOST_DURATION_DAYS",
        "BOOST_SLOTS_PER_PAGE",
        "BOOST_MIN_ACCOUNT_AGE_HOURS",
    ),
    "Ranking": ("W_FRESH", "W_ACT", "W_QUAL", "W_REPORT", "ACTIVITY_CAP", "FRESH_HALF_LIFE_DAYS"),
    "Maps and location": (
        "NEARBY_RADII",
        "CAMPUS_AUTOLINK_RADIUS_M",
        "LOCATION_SNAP_M",
        "WALKING_M_PER_MIN",
        "MAP_TILE_URL",
        "MAP_ATTRIBUTION",
    ),
    "Trust and moderation": (
        "NEW_SELLER_REVIEW_COUNT",
        "REPORTS_AUTO_HIDE",
        "FIRST_CONTACT_MIN_ACCOUNT_AGE_HOURS",
        "CHAT_NEW_ACCOUNT_DAYS",
        "CHAT_NEW_ACCOUNT_DAILY_LIMIT",
        "GUEST_CHAT_MESSAGE_LIMIT",
        "MAX_PHOTOS",
        "MAX_UPLOAD_MB",
    ),
    "Appearance": ("THEMES_OFFERED",),
    "Telemetry and growth": (
        "TELEMETRY_RAW_RETENTION_DAYS",
        "AMBASSADOR_BONUS_BOOSTS",
        "RENT_CHECK_MIN_SAMPLES",
    ),
    "External content": (
        "CAMPUS_PLACES_RADIUS_M",
        "PLACES_REFRESH_DAYS",
        "IMPORT_PLACE_PHONES",
        "PLACE_REPORTS_AUTO_HIDE",
        "REMOTIVE_FETCHES_PER_DAY",
        "REMOTIVE_LOCATION_KEYWORDS",
        "REMOTIVE_CATEGORIES",
        "EXTERNAL_JOB_MAX_AGE_DAYS",
    ),
}
