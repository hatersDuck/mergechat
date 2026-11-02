"""Message idempotency helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.domain.message import RawMessage
from mergechat.storage import repositories


async def is_duplicate(session: AsyncSession, message: RawMessage) -> bool:
    return await repositories.message_exists(
        session,
        message.platform,
        message.external_chat_id,
        message.external_message_id,
    )
