"""Run the Max passive listener for a stored account."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal

from mergechat.config import get_settings
from mergechat.connectors.registry import ConnectorRegistry
from mergechat.logging import configure_logging
from mergechat.processing.ingestion import IngestionService
from mergechat.storage import repositories
from mergechat.storage.database import (
    create_engine,
    create_session_factory,
    ensure_schema,
)

logger = logging.getLogger(__name__)


async def run(account_id: str | None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    await ensure_schema(settings)

    try:
        async with factory() as session:
            if account_id is None:
                account = await repositories.create_account(session, "Max listener")
                await session.commit()
                account_id = account.id
                logger.info("created account", extra={"account_id": account_id})
            else:
                account = await repositories.get_account(session, account_id)
                if account is None:
                    raise SystemExit(f"Account {account_id} not found.")

        registry = ConnectorRegistry(settings, factory, IngestionService(factory))
        result = await registry.connect(account_id)
        print(f"status={result.status} connected={result.connected}")
        if result.qr_link:
            print(f"QR: {result.qr_link}")

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)

        await stop.wait()
        await registry.stop_all()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", help="Existing account id; created if omitted.")
    args = parser.parse_args()
    asyncio.run(run(args.account_id))


if __name__ == "__main__":
    main()
