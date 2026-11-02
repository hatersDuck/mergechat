"""Lifecycle management for platform connectors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mergechat.config import Settings
from mergechat.connectors.max.connector import MaxConnector
from mergechat.connectors.max.session import MaxSessionStore
from mergechat.domain.chat import ChatInfo, HealthStatus
from mergechat.domain.message import RawMessage
from mergechat.logging import redact
from mergechat.processing.ingestion import IngestionService
from mergechat.security.sessions import SessionCipher, SessionKeyMissingError
from mergechat.storage import repositories

logger = logging.getLogger(__name__)


class AccountNotFoundError(LookupError):
    pass


@dataclass(slots=True)
class ConnectResult:
    account_id: str
    status: str
    connected: bool
    qr_link: str | None


class ConnectorRegistry:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        ingestion: IngestionService,
        session_store: MaxSessionStore | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._ingestion = ingestion
        self._session_store = session_store or MaxSessionStore(settings)
        self._connectors: dict[str, MaxConnector] = {}

    def get(self, account_id: str) -> MaxConnector | None:
        return self._connectors.get(account_id)

    async def connect(self, account_id: str) -> ConnectResult:
        try:
            SessionCipher.from_settings(self._settings)
        except SessionKeyMissingError as exc:
            raise RuntimeError(
                "Configure a strong MERGECHAT_SESSION_ENCRYPTION_KEY before "
                "connecting a Max account."
            ) from exc

        existing = self._connectors.get(account_id)
        if existing is not None:
            health = await existing.health_check()
            if existing.is_active:
                return ConnectResult(
                    account_id=account_id,
                    status=health.status,
                    connected=health.connected,
                    qr_link=None if health.connected else existing.qr_link,
                )
            await existing.stop()
            self._connectors.pop(account_id, None)

        async with self._session_factory() as session:
            account = await repositories.get_account(session, account_id)
            if account is None:
                raise AccountNotFoundError(account_id)
            account.status = "connecting"
            encrypted_session = account.encrypted_session_data
            selected = await repositories.get_selected_chat_ids(session, account_id)
            await session.commit()

        try:
            await self._session_store.restore(account_id, encrypted_session)
        except Exception as exc:
            await self._set_account_state(account_id, "error", str(exc))
            raise

        connector = MaxConnector(
            account_id,
            self._settings,
            selected_chat_ids=set(selected),
            on_message=lambda message: self._ingest(account_id, message),
            on_delete=lambda chat_id, ids: self._mark_deleted(
                account_id, chat_id, ids
            ),
            on_state=lambda status, error: self._set_account_state(
                account_id, status, error
            ),
            on_connected=lambda: self._handle_connected(account_id),
        )
        self._connectors[account_id] = connector

        try:
            await connector.connect()
        except Exception as exc:
            await self._set_account_state(account_id, "error", str(exc))
            raise

        health = await connector.health_check()
        status = health.status
        if health.connected:
            status = "connected"
        elif connector.qr_link:
            status = "pending_auth"
        await self._set_account_state(account_id, status, health.error)
        return ConnectResult(
            account_id=account_id,
            status=status,
            connected=health.connected,
            qr_link=None if health.connected else connector.qr_link,
        )

    async def _ingest(self, account_id: str, message: RawMessage) -> None:
        await self._ingestion.ingest(account_id, message)

    async def _mark_deleted(
        self, account_id: str, chat_id: str, message_ids: list[str]
    ) -> None:
        await self._ingestion.mark_deleted(account_id, chat_id, message_ids)

    async def _handle_connected(self, account_id: str) -> None:
        connector = self._connectors.get(account_id)
        async with self._session_factory() as session:
            selected = await repositories.get_selected_chat_ids(session, account_id)
            account = await repositories.get_account(session, account_id)
            if account is not None:
                account.status = "connected"
                account.last_health_check = datetime.now(UTC)
                account.last_error = None
            await session.commit()

        if connector is not None:
            await connector.subscribe(selected)

        try:
            encrypted = await self._session_store.persist(account_id)
        except Exception:
            logger.exception(
                "failed to persist encrypted Max session",
                extra={"account_id": account_id},
            )
            return
        if encrypted is None:
            return

        async with self._session_factory() as session:
            account = await repositories.get_account(session, account_id)
            if account is not None:
                await repositories.set_encrypted_session(session, account, encrypted)
            await session.commit()

    async def list_chats(self, account_id: str) -> list[ChatInfo]:
        connector = self._connectors.get(account_id)
        if connector is None:
            return []
        chats = await connector.list_chats()
        async with self._session_factory() as session:
            selected = set(
                await repositories.get_selected_chat_ids(session, account_id)
            )
            for chat in chats:
                chat.selected = chat.external_chat_id in selected
                await repositories.upsert_chat(session, account_id, chat)
            await session.commit()
        return chats

    async def subscribe(self, account_id: str, chat_ids: list[str]) -> None:
        connector = self._connectors.get(account_id)
        if connector is not None:
            await connector.subscribe(chat_ids)

    async def start_listener(self, account_id: str) -> ConnectResult:
        async with self._session_factory() as session:
            selected = await repositories.get_selected_chat_ids(session, account_id)
        if not selected:
            raise ValueError("Select at least one chat before starting the listener.")
        result = await self.connect(account_id)
        connector = self._connectors.get(account_id)
        if connector is not None:
            await connector.subscribe(selected)
        return result

    async def stop_listener(self, account_id: str) -> None:
        connector = self._connectors.get(account_id)
        if connector is not None:
            await connector.subscribe([])

    async def health(self, account_id: str) -> HealthStatus:
        connector = self._connectors.get(account_id)
        if connector is None:
            async with self._session_factory() as session:
                account = await repositories.get_account(session, account_id)
                if account is None:
                    raise AccountNotFoundError(account_id)
                return HealthStatus(
                    connected=False,
                    status=account.status,
                    error=account.last_error,
                    reconnect_count=account.reconnect_count,
                )
        status = await connector.health_check()
        async with self._session_factory() as session:
            account = await repositories.get_account(session, account_id)
            if account is not None:
                account.reconnect_count = status.reconnect_count
                account.last_health_check = datetime.now(UTC)
                await session.commit()
        return status

    async def disconnect(self, account_id: str) -> None:
        connector = self._connectors.pop(account_id, None)
        if connector is not None:
            await connector.stop()
        await self._set_account_state(account_id, "disconnected", None)

    async def revoke_session(self, account_id: str) -> None:
        """Disconnect and remove the local encrypted/live session material."""
        await self.disconnect(account_id)
        self._session_store.delete(account_id)
        async with self._session_factory() as session:
            await repositories.clear_account_session(session, account_id)
            await session.commit()

    async def delete_account(self, account_id: str) -> bool:
        await self.disconnect(account_id)
        self._session_store.delete(account_id)
        async with self._session_factory() as session:
            deleted = await repositories.delete_account(session, account_id)
            await session.commit()
        return deleted

    async def stop_all(self) -> None:
        account_ids = list(self._connectors)
        for account_id in account_ids:
            await self.disconnect(account_id)

    async def _set_account_state(
        self, account_id: str, status: str, error: str | None
    ) -> None:
        async with self._session_factory() as session:
            account = await repositories.get_account(session, account_id)
            if account is not None:
                account.status = status
                account.last_error = redact(error) if error else None
                await session.commit()
