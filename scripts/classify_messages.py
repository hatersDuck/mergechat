"""Classify pending stored messages through JEV."""

from __future__ import annotations

import argparse
import asyncio

from mergechat.config import get_settings
from mergechat.jev.service import JevService
from mergechat.logging import configure_logging
from mergechat.processing.classifier import ClassifierService
from mergechat.storage.database import (
    create_engine,
    create_session_factory,
    ensure_schema,
)


async def run(account_id: str | None, limit: int) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    await ensure_schema(settings)
    jev_service = JevService(settings)
    try:
        classifier = ClassifierService(factory, jev_service)
        result = await classifier.classify_pending(
            account_id=account_id, limit=limit
        )
        print(
            f"processed={result.processed} failed={result.failed} run={result.run_id}"
        )
    finally:
        await jev_service.aclose()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    asyncio.run(run(args.account_id, args.limit))


if __name__ == "__main__":
    main()
