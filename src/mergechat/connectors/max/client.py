"""Factory for configured PyMax WebClient instances."""

from __future__ import annotations

from pymax import (
    ConsolePasswordProvider,
    ExtraConfig,
    PasswordProvider,
    QrAuthFlow,
    QrHandler,
    SyncOverrides,
    WebClient,
)

from mergechat.config import Settings


def build_web_client(
    settings: Settings,
    account_id: str,
    qr_handler: QrHandler,
    password_provider: PasswordProvider | None = None,
) -> WebClient:
    settings.max_work_path.mkdir(parents=True, exist_ok=True)
    return WebClient(
        work_dir=str(settings.max_work_path),
        session_name=f"{account_id}.db",
        auth_flow=QrAuthFlow(
            qr_handler, password_provider or ConsolePasswordProvider()
        ),
        extra_config=ExtraConfig(
            sync=SyncOverrides(chats_sync=-1),
            reconnect=True,
            log_level=settings.log_level,
        ),
    )
