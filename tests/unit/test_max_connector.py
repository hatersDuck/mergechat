from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pymax import Chat, Message

from mergechat.config import Settings
from mergechat.connectors.max.connector import MaxConnectionError, MaxConnector
from mergechat.domain.message import RawMessage


class FakeWebClient:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.chats = [
            Chat(
                id=555,
                type="CHAT",
                status="ACTIVE",
                owner=1,
                title="Orders",
                participants_count=10,
                messages_count=20,
            ),
            Chat(
                id=999,
                type="DIALOG",
                status="ACTIVE",
                owner=1,
                title="Direct",
            ),
        ]
        self.is_connected = False
        self._stop = asyncio.Event()

    def _decorator(self, name: str):
        def register(callback):
            self.handlers[name] = callback
            return callback

        return register

    def on_start(self):
        return self._decorator("start")

    def on_message(self):
        return self._decorator("message")

    def on_message_edit(self):
        return self._decorator("edit")

    def on_message_delete(self):
        return self._decorator("delete")

    def on_disconnect(self):
        return self._decorator("disconnect")

    def on_error(self):
        return self._decorator("error")

    async def start(self) -> None:
        self.is_connected = True
        await self.handlers["start"](self)
        await self._stop.wait()

    async def stop(self) -> None:
        self.is_connected = False
        self._stop.set()

    async def fetch_chats(self) -> list[Chat]:
        return self.chats


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        session_encryption_key="test",
        jev_api_key="",
        max_connect_timeout_seconds=2,
        _env_file=None,
    )


async def test_connect_lists_group_chats_and_filters_subscription(settings) -> None:
    received: list[RawMessage] = []
    states: list[str] = []
    fake = FakeWebClient()

    connector = MaxConnector(
        "account-1",
        settings,
        selected_chat_ids={"555"},
        on_message=lambda message: _collect(received, message),
        on_state=lambda status, error: _collect_state(states, status, error),
        client_factory=lambda *_args: fake,
    )

    await connector.connect()
    health = await connector.health_check()
    assert health.connected is True

    chats = await connector.list_chats()
    assert [chat.external_chat_id for chat in chats] == ["555"]
    assert chats[0].selected is True

    selected = Message(
        id=1, chat_id=555, sender=7, text="2 horses", time=1_779_805_553_478, type="TEXT"
    )
    other = Message(
        id=2, chat_id=999, sender=7, text="private", time=1_779_805_553_478, type="TEXT"
    )
    await fake.handlers["message"](selected, fake)
    await fake.handlers["message"](other, fake)

    assert [message.external_chat_id for message in received] == ["555"]

    await connector.subscribe(["999"])
    await fake.handlers["message"](other, fake)
    assert len(received) == 2

    await connector.stop()
    assert states[-1] == "disconnected"


async def test_connect_failure_is_propagated(settings) -> None:
    class FailingClient(FakeWebClient):
        async def start(self) -> None:
            await self.handlers["start"](self)
            raise RuntimeError("authentication failed")

    fake = FailingClient()
    connector = MaxConnector(
        "account-1",
        settings,
        client_factory=lambda *_args: fake,
    )

    with pytest.raises(MaxConnectionError):
        await connector.connect()

    await connector.stop()


async def _collect(target: list[RawMessage], message: RawMessage) -> None:
    target.append(message)


async def _collect_state(
    target: list[str], status: str, error: str | None
) -> None:
    target.append(status)
