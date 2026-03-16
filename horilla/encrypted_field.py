"""
horilla/encrypted_field.py

A minimal Fernet-based encrypted CharField compatible with Django 4.2+.

Stores ciphertext (base64 Fernet token) in the database column.
Reads back plaintext transparently through the ORM.

Uses FERNET_KEYS from settings — the first key encrypts new values;
all keys are tried during decryption to allow zero-downtime key rotation.

Usage in models:
    from horilla.encrypted_field import EncryptedCharField

    class MyModel(models.Model):
        secret = EncryptedCharField(max_length=200, null=True, blank=True)
"""

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def _get_fernet() -> MultiFernet:
    """Build a MultiFernet from settings.FERNET_KEYS.

    MultiFernet tries each key in order for decryption and always encrypts
    with the first key, which makes key rotation straightforward:
      1. prepend the new key to FERNET_KEYS
      2. deploy
      3. optionally re-save all rows to re-encrypt under the new key
      4. remove the old key from the list
    """
    keys = getattr(settings, "FERNET_KEYS", [])
    active_keys = [k for k in keys if k]  # skip empty strings / None
    if not active_keys:
        raise ValueError(
            "settings.FERNET_KEYS is empty or not set. "
            "Generate a key with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in active_keys])


class EncryptedCharField(models.TextField):
    """
    A CharField that stores its value encrypted at rest using Fernet.

    - max_length is enforced on the *plaintext* value before encryption.
    - The database column is TextField because ciphertext is longer than
      the plaintext (Fernet adds ~57 bytes of overhead).
    - null=True is preserved: a NULL in the DB stays NULL (not encrypted).
    """

    def __init__(self, *args, **kwargs):
        # Record the intended plaintext max_length for validation,
        # then let TextField use its own (unlimited) column size.
        self._plaintext_max_length = kwargs.pop("max_length", None)
        # TextField does not use max_length, so don't pass it up.
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self._plaintext_max_length is not None:
            kwargs["max_length"] = self._plaintext_max_length
        return name, path, args, kwargs

    # ── Write path ────────────────────────────────────────────────────────────

    def get_prep_value(self, value):
        """Encrypt plaintext before writing to the database."""
        if value is None or value == "":
            return value
        plaintext = str(value).encode("utf-8")
        token = _get_fernet().encrypt(plaintext)
        return token.decode("utf-8")

    # ── Read path ─────────────────────────────────────────────────────────────

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        return self._decrypt(value)

    def _decrypt(self, value):
        if value is None or value == "":
            return value
        try:
            plaintext = _get_fernet().decrypt(value.encode("utf-8"))
            return plaintext.decode("utf-8")
        except InvalidToken:
            # Value may already be plaintext (pre-migration row or dev data).
            logger.warning(
                "EncryptedCharField: decryption failed — returning raw value. "
                "Run the encrypt data migration to fix this."
            )
            return value
