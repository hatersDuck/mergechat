"""Normalized message ingestion."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mergechat.domain.message import RawMessage
from mergechat.storage import repositories
from mergechat.storage.models import AccountSession

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestResult:
    message_id: str
    created: bool


class IngestionService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def ingest(self, account_id: str, message: RawMessage) -> IngestResult:
        async with self._session_factory() as session:
            try:
                row, created = await repositories.insert_message(
                    session, account_id, message
                )
                account = await session.get(AccountSession, account_id)
                if account is not None and created:
                    account.last_message_at = datetime.now(UTC)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "failed to ingest message",
                    extra={
                        "account_id": account_id,
                        "external_chat_id": message.external_chat_id,
                        "external_message_id": message.external_message_id,
                    },
                )
                raise

        logger.info(
            "message ingested",
            extra={
                "account_id": account_id,
                "external_chat_id": message.external_chat_id,
                "external_message_id": message.external_message_id,
                "was_created": created,
                "event_type": message.event_type,
            },
        )
        return IngestResult(message_id=row.id, created=created)

    async def mark_deleted(
        self,
        account_id: str,
        external_chat_id: str,
        external_message_ids: Sequence[str],
    ) -> int:
        async with self._session_factory() as session:
            count = await repositories.mark_messages_deleted(
                session, account_id, external_chat_id, external_message_ids
            )
            await session.commit()
        logger.info(
            "message(s) marked deleted",
            extra={
                "account_id": account_id,
                "external_chat_id": external_chat_id,
                "count": count,
            },
        )
        return count
