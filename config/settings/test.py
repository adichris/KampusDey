from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key"
FIELD_ENCRYPTION_KEY = "bXl0ZXN0a2V5bXl0ZXN0a2V5bXl0ZXN0a2V5bXl0ZXM="
DATABASES = {"default": env.db("TEST_DATABASE_URL", default="sqlite://:memory:")}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "private": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
AXES_ENABLED = False
RATELIMIT_ENABLE = True
ALLOWED_HOSTS = ["testserver", "localhost"]
SITE_URL = "http://testserver"
GEOIP_PATH = str(BASE_DIR / "tests" / "no-geoip")
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"level": "WARNING"}}
TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django_cotton.cotton_loader.Loader",
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
