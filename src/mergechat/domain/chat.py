"""Chat and connector health DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatInfo(BaseModel):
    """A platform-independent chat descriptor."""

    model_config = ConfigDict(extra="ignore")

    external_chat_id: str
    title: str | None = None
    chat_type: str = "CHAT"
    participants_count: int = 0
    messages_count: int = 0
    selected: bool = False


class HealthStatus(BaseModel):
    """Connector health snapshot."""

    connected: bool = False
    status: str = "created"
    last_event_at: datetime | None = None
    reconnect_count: int = 0
    error: str | None = None
