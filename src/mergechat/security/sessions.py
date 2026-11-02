"""Encryption for connector session files.

Phase 0 accepts an environment-provided passphrase. New ciphertext carries a
random salt and uses PBKDF2-HMAC-SHA256; legacy ciphertext remains readable.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from mergechat.config import Settings

_MAGIC = b"MC1:"
_SALT_BYTES = 16
_KDF_ITERATIONS = 390_000
_PLACEHOLDER_KEYS = {
    "change-me-to-a-long-random-passphrase",
    "changeme",
    "password",
    "secret",
}


class SessionKeyMissingError(RuntimeError):
    """Raised when session encryption is requested without a usable key."""


class SessionDecryptionError(RuntimeError):
    """Raised when encrypted session data cannot be decrypted."""


class SessionCipher:
    def __init__(self, passphrase: str) -> None:
        candidate = passphrase.strip()
        if not candidate:
            raise SessionKeyMissingError(
                "MERGECHAT_SESSION_ENCRYPTION_KEY is required to persist sessions."
            )
        if len(candidate) < 12 or candidate.lower() in _PLACEHOLDER_KEYS:
            raise SessionKeyMissingError(
                "MERGECHAT_SESSION_ENCRYPTION_KEY is weak or still a placeholder."
            )
        self._passphrase = candidate.encode("utf-8")
        self._legacy_fernet = Fernet(self._legacy_key(candidate))

    @classmethod
    def from_settings(cls, settings: Settings) -> SessionCipher:
        return cls(settings.session_encryption_key.get_secret_value())

    @staticmethod
    def _legacy_key(passphrase: str) -> bytes:
        raw = passphrase.encode("utf-8")
        try:
            if len(raw) == 44:
                base64.urlsafe_b64decode(raw)
                return raw
        except (ValueError, TypeError):
            pass
        return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())

    @staticmethod
    def _derive_key(passphrase: bytes, salt: bytes) -> bytes:
        digest = hashlib.pbkdf2_hmac(
            "sha256", passphrase, salt, _KDF_ITERATIONS
        )
        return base64.urlsafe_b64encode(digest)

    def encrypt(self, data: bytes) -> bytes:
        salt = secrets.token_bytes(_SALT_BYTES)
        token = Fernet(self._derive_key(self._passphrase, salt)).encrypt(data)
        return _MAGIC + salt + token

    def decrypt(self, data: bytes) -> bytes:
        try:
            if data.startswith(_MAGIC):
                body = data[len(_MAGIC) :]
                if len(body) <= _SALT_BYTES:
                    raise SessionDecryptionError("Encrypted session data is truncated.")
                salt, token = body[:_SALT_BYTES], body[_SALT_BYTES:]
                return Fernet(self._derive_key(self._passphrase, salt)).decrypt(token)
            return self._legacy_fernet.decrypt(data)
        except InvalidToken as exc:
            raise SessionDecryptionError(
                "Encrypted session data could not be decrypted with the configured key."
            ) from exc
