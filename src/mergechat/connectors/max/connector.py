"""Max connector implementation over PyMax's WebClient."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pymax import Chat, Message, MessageDeleteEvent, WebClient

from mergechat.config import Settings
from mergechat.connectors.max.client import build_web_client
from mergechat.connectors.max.normalizer import normalize_message
from mergechat.domain.chat import ChatInfo, HealthStatus
from mergechat.domain.message import RawMessage
from mergechat.logging import redact

logger = logging.getLogger(__name__)

MessageCallback = Callable[[RawMessage], Awaitable[None]]
DeleteCallback = Callable[[str, list[str]], Awaitable[None]]
StateCallback = Callable[[str, str | None], Awaitable[None]]
ConnectedCallback = Callable[[], Awaitable[None]]
ClientFactory = Callable[[Settings, str, "ApiQrHandler"], WebClient]


class MaxConnectionError(RuntimeError):
    """Raised when the Max client fails during authentication or startup."""


class ApiQrHandler:
    """Capture the Max QR link so the onboarding API can return it."""

    def __init__(self) -> None:
        self.qr_link: str | None = None
        self.shown = asyncio.Event()

    async def show_qr(self, qr_url: str) -> None:
        self.qr_link = qr_url
        self.shown.set()


class MaxConnector:
    def __init__(
        self,
        account_id: str,
        settings: Settings,
        *,
        selected_chat_ids: set[str] | None = None,
        on_message: MessageCallback | None = None,
        on_delete: DeleteCallback | None = None,
        on_state: StateCallback | None = None,
        on_connected: ConnectedCallback | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.account_id = account_id
        self._settings = settings
        self._selected = {str(value) for value in (selected_chat_ids or set())}
        self._on_message = on_message
        self._on_delete = on_delete
        self._on_state = on_state
        self._on_connected = on_connected
        self._client_factory = client_factory or build_web_client

        self.qr_handler = ApiQrHandler()
        self._client: WebClient | None = None
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._status = "created"
        self._last_event_at: datetime | None = None
        self._last_error: str | None = None
        self._reconnect_count = 0

    @property
    def qr_link(self) -> str | None:
        return self.qr_handler.qr_link

    @property
    def is_active(self) -> bool:
        return self._task is not None and not self._task.done()

    async def connect(self) -> None:
        if self._client is not None and self._client.is_connected:
            return
        if self._task is not None and not self._task.done():
            return

        self._status = "connecting"
        self._last_error = None
        self._ready.clear()
        self.qr_handler = ApiQrHandler()
        self._client = self._client_factory(
            self._settings, self.account_id, self.qr_handler
        )
        self._register_handlers(self._client)
        self._task = asyncio.create_task(
            self._run(), name=f"max-connector-{self.account_id}"
        )

        ready_task = asyncio.create_task(self._ready.wait())
        qr_task = asyncio.create_task(self.qr_handler.shown.wait())
        timed_out = False
        try:
            done, _ = await asyncio.wait(
                {ready_task, qr_task},
                timeout=self._settings.max_connect_timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            timed_out = not done
        finally:
            for task in (ready_task, qr_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(ready_task, qr_task, return_exceptions=True)

        if timed_out:
            logger.warning(
                "Max connector did not become ready before timeout",
                extra={"account_id": self.account_id},
            )
            self._status = "connecting"

        if self._status == "error":
            raise MaxConnectionError(
                self._last_error or "Max authentication failed."
            )

        if self._status == "connected":
            await self.subscribe(sorted(self._selected))

    async def _run(self) -> None:
        assert self._client is not None
        try:
            await self._client.start()
        except asyncio.CancelledError:
            self._status = "disconnected"
            raise
        except Exception as exc:
            self._status = "error"
            self._last_error = redact(str(exc))
            logger.exception(
                "Max connector stopped with error",
                extra={"account_id": self.account_id},
            )
            await self._emit_state()
        finally:
            if self._status != "error":
                self._status = "disconnected"
            self._ready.set()

    def _register_handlers(self, client: WebClient) -> None:
        @client.on_start()
        async def _on_start(_: WebClient) -> None:
            self._status = "connected"
            self._last_error = None
            self.qr_handler.qr_link = None
            self._ready.set()
            logger.info("Max connector started", extra={"account_id": self.account_id})
            if self._on_connected is not None:
                try:
                    await self._on_connected()
                except Exception:
                    logger.exception(
                        "Max connected callback failed",
                        extra={"account_id": self.account_id},
                    )

        @client.on_message()
        async def _on_message(message: Message, _: WebClient) -> None:
            await self._handle_message(message, event_type="create")

        @client.on_message_edit()
        async def _on_message_edit(message: Message, _: WebClient) -> None:
            await self._handle_message(message, event_type="edit")

        @client.on_message_delete()
        async def _on_message_delete(event: MessageDeleteEvent, _: WebClient) -> None:
            if str(event.chat_id) not in self._selected:
                return
            if self._on_delete is not None:
                try:
                    await self._on_delete(
                        str(event.chat_id),
                        [str(message_id) for message_id in event.message_ids],
                    )
                except Exception:
                    logger.exception(
                        "failed to handle Max delete event",
                        extra={"account_id": self.account_id},
                    )

        @client.on_disconnect()
        async def _on_disconnect(
            exc: Exception, reconnect: bool, delay: float
        ) -> None:
            if reconnect:
                self._reconnect_count += 1
            self._status = "reconnecting" if reconnect else "disconnected"
            self._last_error = redact(str(exc))
            logger.warning(
                "Max disconnected",
                extra={
                    "account_id": self.account_id,
                    "reconnect": reconnect,
                    "delay": delay,
                },
            )
            await self._emit_state()

        @client.on_error()
        async def _on_error(exc: Exception, context: object) -> None:
            logger.error(
                "Max dispatch error",
                extra={
                    "account_id": self.account_id,
                    "error": str(exc),
                    "event": str(getattr(context, "event_type", "")),
                },
            )

    async def _handle_message(self, message: Message, *, event_type: str) -> None:
        if message.chat_id is None:
            return
        if str(message.chat_id) not in self._selected:
            return
        self._last_event_at = datetime.now(UTC)
        chat = self._find_chat(message.chat_id)
        raw = normalize_message(message, chat=chat, event_type=event_type)
        if raw is None or self._on_message is None:
            return
        try:
            await self._on_message(raw)
        except Exception:
            logger.exception(
                "failed to handle Max message",
                extra={
                    "account_id": self.account_id,
                    "external_message_id": raw.external_message_id,
                },
            )

    def _find_chat(self, chat_id: int) -> Chat | None:
        if self._client is None:
            return None
        for chat in self._client.chats or []:
            if chat.id == chat_id:
                return chat
        return None

    async def _emit_state(self) -> None:
        if self._on_state is not None:
            try:
                await self._on_state(self._status, self._last_error)
            except Exception:
                logger.exception(
                    "failed to persist connector state",
                    extra={"account_id": self.account_id},
                )

    async def list_chats(self) -> list[ChatInfo]:
        if self._client is None:
            return []
        chats = self._client.chats
        if chats is None:
            chats = await self._client.fetch_chats()
        result: list[ChatInfo] = []
        for chat in chats or []:
            chat_type = getattr(chat.type, "value", chat.type)
            if str(chat_type) != "CHAT":
                continue
            result.append(
                ChatInfo(
                    external_chat_id=str(chat.id),
                    title=chat.title,
                    chat_type=str(chat_type),
                    participants_count=chat.participants_count,
                    messages_count=chat.messages_count,
                    selected=str(chat.id) in self._selected,
                )
            )
        return result

    async def subscribe(self, chat_ids: list[str]) -> None:
        self._selected = {str(chat_id) for chat_id in chat_ids}
        logger.info(
            "Max subscription updated",
            extra={"account_id": self.account_id, "chats": len(self._selected)},
        )

    async def health_check(self) -> HealthStatus:
        connected = bool(self._client is not None and self._client.is_connected)
        return HealthStatus(
            connected=connected,
            status=self._status,
            last_event_at=self._last_event_at,
            reconnect_count=self._reconnect_count,
            error=self._last_error,
        )

    def normalize(self, message: object) -> RawMessage | None:
        if not isinstance(message, Message):
            return None
        return normalize_message(message, chat=self._find_chat(message.chat_id or 0))

    async def stop(self) -> None:
        self._status = "disconnected"
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.stop()
        if self._task is not None and not self._task.done():
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self._task, timeout=5)
            if not self._task.done():
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
        self._task = None
        await self._emit_state()
