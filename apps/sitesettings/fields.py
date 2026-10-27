"""Fernet-encrypted text field (§8.3).

Values are encrypted with `FIELD_ENCRYPTION_KEY` before they reach the database. Several keys
can be given comma-separated (newest first) to rotate: MultiFernet decrypts with any key and
encrypts with the first. Run `manage.py rotate_field_keys` after adding a new key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

PREFIX = "fernet:"


def get_fernet() -> MultiFernet:
    keys = [k.strip() for k in (settings.FIELD_ENCRYPTION_KEY or "").split(",") if k.strip()]
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(value: str) -> str:
    return PREFIX + get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value.startswith(PREFIX):
        return value
    try:
        return get_fernet().decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken:
        return ""


class EncryptedTextField(models.TextField):
    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        return decrypt(value)

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        if value.startswith(PREFIX):
            return value
        return encrypt(value)
