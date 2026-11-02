"""Convert PyMax payloads into platform-independent messages."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pymax import Chat, Message

from mergechat.domain.message import RawMessage

logger = logging.getLogger(__name__)


def _timestamp(value: int | float | None) -> datetime:
    if not value or value <= 0:
        return datetime.now(UTC)
    seconds = float(value)
    if seconds > 10_000_000_000:
        seconds /= 1000
    return datetime.fromtimestamp(seconds, tz=UTC)


def _attachment_metadata(message: Message) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for attachment in message.attaches:
        try:
            payload = attachment.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        except Exception:
            logger.warning(
                "failed to serialize attachment",
                extra={"message_id": str(message.id)},
                exc_info=True,
            )
            payload = {"type": getattr(attachment, "type", "unknown")}
        attachments.append(payload)
    return attachments


def _raw_payload(message: Message) -> dict[str, Any]:
    try:
        return message.model_dump(mode="json", by_alias=True, exclude_none=True)
    except Exception:
        logger.warning(
            "failed to serialize raw message payload",
            extra={"message_id": str(message.id)},
            exc_info=True,
        )
        return {
            "id": str(message.id),
            "chatId": message.chat_id,
            "time": message.time,
            "type": message.type,
            "text": message.text,
        }


def normalize_message(
    message: Message,
    *,
    chat: Chat | None = None,
    event_type: str = "create",
) -> RawMessage | None:
    """Normalize a PyMax message, returning ``None`` for unusable payloads."""

    if message.chat_id is None:
        logger.warning("skipping message without chat_id", extra={"message_id": str(message.id)})
        return None

    return RawMessage(
        platform="max",
        external_message_id=str(message.id),
        external_chat_id=str(message.chat_id),
        chat_title=chat.title if chat is not None else None,
        author_external_id=str(message.sender) if message.sender is not None else None,
        author_name=None,
        text=message.text or "",
        timestamp=_timestamp(message.time),
        attachments=_attachment_metadata(message),
        raw_payload=_raw_payload(message),
        event_type=event_type,  # type: ignore[arg-type]
    )
