from __future__ import annotations

import pytest

from mergechat.config import Settings
from mergechat.security.sessions import (
    SessionCipher,
    SessionDecryptionError,
    SessionKeyMissingError,
)


def test_session_cipher_roundtrip() -> None:
    cipher = SessionCipher("secret-passphrase")
    encrypted = cipher.encrypt(b"session bytes")
    assert encrypted != b"session bytes"
    assert cipher.decrypt(encrypted) == b"session bytes"


def test_missing_key_is_rejected() -> None:
    with pytest.raises(SessionKeyMissingError):
        SessionCipher("")


def test_wrong_key_is_rejected() -> None:
    encrypted = SessionCipher("one-long-secret-key").encrypt(b"data")
    with pytest.raises(SessionDecryptionError):
        SessionCipher("two-long-secret-key").decrypt(encrypted)


def test_placeholder_key_is_rejected() -> None:
    with pytest.raises(SessionKeyMissingError):
        SessionCipher("change-me-to-a-long-random-passphrase")


def test_settings_reports_key_presence() -> None:
    missing = Settings(session_encryption_key="", _env_file=None)
    present = Settings(session_encryption_key="key", _env_file=None)
    assert missing.has_session_encryption is False
    assert present.has_session_encryption is True
