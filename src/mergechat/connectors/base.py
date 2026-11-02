"""Platform-independent connector interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mergechat.domain.chat import ChatInfo, HealthStatus
from mergechat.domain.message import RawMessage


@runtime_checkable
class Connector(Protocol):
    async def connect(self) -> None: ...

    async def stop(self) -> None: ...

    async def list_chats(self) -> list[ChatInfo]: ...

    async def subscribe(self, chat_ids: list[str]) -> None: ...

    async def health_check(self) -> HealthStatus: ...

    def normalize(self, message: object) -> RawMessage | None: ...
