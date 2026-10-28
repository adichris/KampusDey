"""Media storage that follows the settings: S3 when configured, otherwise the server's disk.

S3 settings come from the admin (Integrations) first, then the AWS_* environment variables.
With neither, public files live in MEDIA_ROOT and are served by `apps.core.views.media`
(or straight from the web server, e.g. an alwaysdata static path), and private files live in
PRIVATE_MEDIA_ROOT and are never served publicly.
"""

from __future__ import annotations

import threading

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage


def s3_config(private: bool = False) -> dict | None:
    """S3 options for the public (or private) bucket, or None for local disk."""
    from apps.sitesettings.models import IntegrationSettings

    integ = IntegrationSettings.get_cached()
    if integ.s3_bucket:
        bucket = integ.s3_private_bucket if private else integ.s3_bucket
        creds = {
            "access_key": integ.s3_access_key_id,
            "secret_key": integ.s3_secret_access_key,
            "endpoint_url": integ.s3_endpoint_url or None,
            "region_name": integ.s3_region or None,
            "custom_domain": None if private else (integ.s3_custom_domain or None),
        }
    elif (
        getattr(settings, "STORAGE_BACKEND", "auto") != "local" and settings.AWS_STORAGE_BUCKET_NAME
    ):
        bucket = settings.PRIVATE_STORAGE_BUCKET if private else settings.AWS_STORAGE_BUCKET_NAME
        creds = {
            "access_key": settings.AWS_ACCESS_KEY_ID,
            "secret_key": settings.AWS_SECRET_ACCESS_KEY,
            "endpoint_url": settings.AWS_S3_ENDPOINT_URL or None,
            "region_name": settings.AWS_S3_REGION_NAME or None,
            "custom_domain": None if private else (settings.AWS_S3_CUSTOM_DOMAIN or None),
        }
    else:
        return None
    if not bucket:
        return None
    options = {
        "bucket_name": bucket,
        "default_acl": None,
        "file_overwrite": False,
        **creds,
    }
    if private:
        options.update(querystring_auth=True, querystring_expire=300)
    else:
        options.update(querystring_auth=False)
    return options


def media_on_s3() -> bool:
    return s3_config() is not None


class SwitchingStorage(Storage):
    """Delegates every call to S3Storage or FileSystemStorage, chosen from current settings."""

    def __init__(self, private: bool = False):
        self.private = private
        self._lock = threading.Lock()
        self._key = object()
        self._backend = None

    def _local(self):
        if self.private:
            return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url="/private/")
        return FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)

    @property
    def backend(self) -> Storage:
        options = s3_config(self.private)
        key = tuple(sorted(options.items())) if options else ("local",)
        if key != self._key:
            with self._lock:
                if options:
                    from storages.backends.s3 import S3Storage

                    self._backend = S3Storage(**options)
                else:
                    self._backend = self._local()
                self._key = key
        return self._backend

    @property
    def is_local(self) -> bool:
        return isinstance(self.backend, FileSystemStorage)

    # Storage API, all delegated.
    def _open(self, name, mode="rb"):
        return self.backend._open(name, mode)

    def _save(self, name, content):
        return self.backend._save(name, content)

    def open(self, name, mode="rb"):
        return self.backend.open(name, mode)

    def save(self, name, content, max_length=None):
        return self.backend.save(name, content, max_length=max_length)

    def get_valid_name(self, name):
        return self.backend.get_valid_name(name)

    def get_alternative_name(self, file_root, file_ext):
        return self.backend.get_alternative_name(file_root, file_ext)

    def get_available_name(self, name, max_length=None):
        return self.backend.get_available_name(name, max_length=max_length)

    def generate_filename(self, filename):
        return self.backend.generate_filename(filename)

    def path(self, name):
        return self.backend.path(name)

    def delete(self, name):
        return self.backend.delete(name)

    def exists(self, name):
        return self.backend.exists(name)

    def listdir(self, path):
        return self.backend.listdir(path)

    def size(self, name):
        return self.backend.size(name)

    def url(self, name):
        return self.backend.url(name)

    def get_accessed_time(self, name):
        return self.backend.get_accessed_time(name)

    def get_created_time(self, name):
        return self.backend.get_created_time(name)

    def get_modified_time(self, name):
        return self.backend.get_modified_time(name)
