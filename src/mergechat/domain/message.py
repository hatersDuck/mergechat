"""Normalized incoming message."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RawMessage(BaseModel):
    """Platform-independent representation of an incoming message."""

    platform: str = "max"
    external_message_id: str
    external_chat_id: str
    chat_title: str | None = None
    author_external_id: str | None = None
    author_name: str | None = None
    text: str = ""
    timestamp: datetime
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    event_type: Literal["create", "edit", "delete"] = "create"

    @field_validator("timestamp")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
