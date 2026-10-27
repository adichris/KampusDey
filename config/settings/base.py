"""Base settings shared by every environment.

Secrets and deployment-specific values come from environment variables (see `.env.example`).
Admin-editable settings live in django-constance (`CONSTANCE_CONFIG` below).
"""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab
from csp.constants import NONCE, SELF
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent
APPS_DIR = BASE_DIR / "apps"

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")
ADMIN_URL = env("ADMIN_URL", default="admin/").strip("/") + "/"
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")
MAP_USER_AGENT = env("MAP_USER_AGENT", default=f"KampusDey/1.0 (+{SITE_URL}/contact)")
DATA_IMPORT_USER_AGENT = f"KampusDey-DataImport/1.0 (+{SITE_URL}/contact)"

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "constance",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "django.contrib.postgres",
]
THIRD_PARTY_APPS = [
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.mfa",
    "phonenumber_field",
    "waffle",
    "django_cotton",
    "django_htmx",
    "django_filters",
    "taggit",
    "imagekit",
    "webpush",
    "axes",
    "auditlog",
    "csp",
    "django_celery_beat",
]
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.locations",
    "apps.sitesettings",
    "apps.contacts",
    "apps.listings",
    "apps.hostels",
    "apps.boosts",
    "apps.engagement",
    "apps.chat",
    "apps.moderation",
    "apps.telemetry",
    "apps.notifications",
    "apps.growth",
    "apps.external",
    "apps.dashboard",
    "apps.pages",
]
# django-cleanup must be last so it sees every model.
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + ["django_cleanup.apps.CleanupConfig"]

SITE_ID = 1
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "waffle.middleware.WaffleMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "apps.locations.middleware.CampusContextMiddleware",
    "apps.accounts.middleware.AccountGatesMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "loaders": [
                (
                    "django.template.loaders.cached.Loader",
                    [
                        "django_cotton.cotton_loader.Loader",
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ],
                )
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "csp.context_processors.nonce",
                "apps.core.context_processors.site",
                "apps.locations.context_processors.campus_context",
            ],
            "builtins": [
                "django_cotton.templatetags.cotton",
                "apps.core.templatetags.kd",
            ],
        },
    }
]

# ---------------------------------------------------------------------------
# Database / cache / broker
# ---------------------------------------------------------------------------
# PostgreSQL in production (DATABASE_URL=postgres://...), SQLite for quick local work.
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    # Without Redis we use the database cache so dedupe keys and rate limits survive
    # process restarts and are shared between the web process and workers.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "kd_cache",
        }
    }

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
# No broker configured → run tasks inline so the app works with just `runserver`.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=not REDIS_URL)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TIMEZONE = "Africa/Accra"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "ranking-every-15-min": {
        "task": "listings.recompute_scores",
        "schedule": timedelta(minutes=15),
    },
    "lifecycle-hourly": {"task": "listings.run_lifecycle", "schedule": timedelta(hours=1)},
    "telemetry-flush-every-minute": {"task": "telemetry.flush", "schedule": timedelta(seconds=60)},
    "telemetry-rollup-nightly": {"task": "telemetry.rollup", "schedule": crontab(hour=1, minute=5)},
    "notifications-email-batch": {
        "task": "notifications.send_email_batch",
        "schedule": timedelta(minutes=15),
    },
    "saved-search-alerts-daily": {
        "task": "engagement.saved_search_alerts",
        "schedule": crontab(hour=7, minute=0),
    },
    "weekly-digest": {
        "task": "growth.weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
    "geolite2-weekly": {
        "task": "locations.update_geolite2",
        "schedule": crontab(hour=3, minute=0, day_of_week=2),
    },
    "locations-quarterly": {
        "task": "locations.quarterly_refresh",
        "schedule": crontab(hour=2, minute=30, day_of_month=1, month_of_year="1,4,7,10"),
    },
    "external-hourly": {"task": "external.run_due_sources", "schedule": timedelta(hours=1)},
    "axes-purge-daily": {"task": "accounts.purge_axes", "schedule": crontab(hour=4, minute=0)},
    "price-range-suggestions-monthly": {
        "task": "moderation.suggest_price_ranges",
        "schedule": crontab(hour=5, minute=0, day_of_month=1),
    },
}

# ---------------------------------------------------------------------------
# Auth / allauth
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "accounts:after_login"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_RATE_LIMITS = {"login_failed": "5/5m/ip", "signup": "10/h/ip"}
ACCOUNT_FORMS = {
    "signup": "apps.accounts.forms.KDSignupForm",
    "login": "apps.accounts.forms.KDLoginForm",
}
ACCOUNT_ADAPTER = "apps.accounts.adapters.AccountAdapter"
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[KampusDey] "
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_PROVIDERS = {}
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APPS": [{"client_id": GOOGLE_CLIENT_ID, "secret": GOOGLE_CLIENT_SECRET, "key": ""}],
        "SCOPE": ["profile", "email"],
    }
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
STAFF_MFA_REQUIRED = env.bool("STAFF_MFA_REQUIRED", default=True)
MFA_TOTP_ISSUER = "KampusDey"

AXES_FAILURE_LIMIT = 8
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_FORM_FIELD = "login"
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ACCESS_FAILURE_LOG = True
AXES_IPWARE_PROXY_COUNT = env.int("AXES_PROXY_COUNT", default=0)

AUDITLOG_DISABLE_REMOTE_ADDR = True  # no raw IPs in application tables

RATELIMIT_USE_CACHE = "default"
RATELIMIT_VIEW = "apps.core.views.ratelimited"
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.E003", "django_ratelimit.W001"]

# ---------------------------------------------------------------------------
# i18n / time
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media / storage
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")
if STORAGE_BACKEND == "s3":
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="auto")
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default=None)
    AWS_QUERYSTRING_AUTH = False
    AWS_DEFAULT_ACL = None
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "private": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("PRIVATE_STORAGE_BUCKET", default=""),
                "querystring_auth": True,
                "querystring_expire": 300,
                "custom_domain": None,
            },
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "private": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(PRIVATE_MEDIA_ROOT), "base_url": "/private/"},
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
NOTES_MAX_PDF_MB = 15
IMAGEKIT_DEFAULT_CACHEFILE_STRATEGY = "imagekit.cachefiles.strategies.Optimistic"

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="KampusDey <no-reply@kampusdey.local>")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# ---------------------------------------------------------------------------
# GeoIP (region hint only)
# ---------------------------------------------------------------------------
GEOIP_PATH = env("GEOIP_PATH", default=str(BASE_DIR / "geoip"))

# ---------------------------------------------------------------------------
# Web push
# ---------------------------------------------------------------------------
WEBPUSH_SETTINGS = {
    "VAPID_PUBLIC_KEY": env("VAPID_PUBLIC_KEY", default=""),
    "VAPID_PRIVATE_KEY": env("VAPID_PRIVATE_KEY", default=""),
    "VAPID_ADMIN_EMAIL": env("VAPID_ADMIN_EMAIL", default="admin@kampusdey.local"),
}

# ---------------------------------------------------------------------------
# Security headers / CSP
# ---------------------------------------------------------------------------
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # HTMX reads the token from the hx-headers attribute instead.


def _tile_host(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url.replace("{s}", "a"))
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""


# Tiles may be served from any host the admin configures, so img-src allows https:.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF, NONCE, "https://challenges.cloudflare.com"],
        "style-src": [SELF],
        "img-src": [SELF, "data:", "blob:", "https:"],
        "font-src": [SELF],
        "connect-src": [SELF, "https://challenges.cloudflare.com"],
        "frame-src": ["https://challenges.cloudflare.com"],
        "worker-src": [SELF],
        "manifest-src": [SELF],
        "object-src": ["'none'"],
        "base-uri": [SELF],
        "form-action": [SELF, "https://accounts.google.com"],
        "frame-ancestors": ["'none'"],
    }
}
CSP_EXTRA_SCRIPT_HOSTS = env.list("CSP_EXTRA_SCRIPT_HOSTS", default=[])
CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"] += CSP_EXTRA_SCRIPT_HOSTS
CONTENT_SECURITY_POLICY["DIRECTIVES"]["connect-src"] += CSP_EXTRA_SCRIPT_HOSTS

# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.05, send_default_pii=False)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# ---------------------------------------------------------------------------
# django-unfold admin
# ---------------------------------------------------------------------------
from .unfold import UNFOLD  # noqa: E402, F401

# ---------------------------------------------------------------------------
# django-constance (admin-editable settings)
# ---------------------------------------------------------------------------
from .constance import (  # noqa: E402, F401
    CONSTANCE_ADDITIONAL_FIELDS,
    CONSTANCE_CONFIG,
    CONSTANCE_CONFIG_FIELDSETS,
)

CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
CONSTANCE_DATABASE_CACHE_BACKEND = None

TAGGIT_CASE_INSENSITIVE = True
PHONENUMBER_DEFAULT_REGION = "GH"
PHONENUMBER_DB_FORMAT = "E164"

# KampusDey specific constants (not admin-editable)
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 3
OTP_RESEND_SECONDS = 60
GEOIP_DOWNLOAD_URL = (
    "https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz"
)
REMOTIVE_HARD_MAX_FETCHES_PER_DAY = 4
