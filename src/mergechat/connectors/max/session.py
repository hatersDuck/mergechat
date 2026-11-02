"""Max session file persistence with encryption at rest."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from mergechat.config import Settings
from mergechat.security.sessions import SessionCipher

logger = logging.getLogger(__name__)


class MaxSessionStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._work_dir = settings.max_work_path
        self._work_dir.mkdir(parents=True, exist_ok=True)

    def path(self, account_id: str) -> Path:
        return self._work_dir / f"{account_id}.db"

    def exists(self, account_id: str) -> bool:
        return self.path(account_id).exists()

    async def restore(self, account_id: str, encrypted: bytes | None) -> bool:
        """Materialize an encrypted session file if the local file is missing."""
        path = self.path(account_id)
        if path.exists():
            return True
        if not encrypted:
            return False
        if not self._settings.has_session_encryption:
            raise RuntimeError(
                "Encrypted Max session exists but "
                "MERGECHAT_SESSION_ENCRYPTION_KEY is not configured."
            )
        cipher = SessionCipher.from_settings(self._settings)
        data = cipher.decrypt(encrypted)
        temporary = path.with_name(f".{path.name}.restore.tmp")
        await asyncio.to_thread(temporary.write_bytes, data)
        with contextlib.suppress(OSError):
            temporary.chmod(0o600)
        await asyncio.to_thread(os.replace, temporary, path)
        return path.stat().st_size > 0

    async def persist(self, account_id: str) -> bytes | None:
        """Read the local session file and return its encrypted form."""
        path = self.path(account_id)
        if not path.exists():
            return None
        data = await asyncio.to_thread(path.read_bytes)
        if not self._settings.has_session_encryption:
            logger.warning(
                "session encryption key is missing; encrypted session not stored",
                extra={"account_id": account_id},
            )
            return None
        return SessionCipher.from_settings(self._settings).encrypt(data)

    def delete(self, account_id: str) -> None:
        path = self.path(account_id)
        if path.exists():
            path.unlink()
