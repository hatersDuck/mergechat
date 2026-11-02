"""Delete messages older than the configured retention window."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from mergechat.config import get_settings
from mergechat.logging import configure_logging
from mergechat.storage import repositories
from mergechat.storage.database import (
    create_engine,
    create_session_factory,
    ensure_schema,
)


async def run(days: int) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    await ensure_schema(settings)
    try:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        async with factory() as session:
            deleted = await repositories.delete_messages_before(session, cutoff)
            await session.commit()
        print(f"deleted={deleted} cutoff={cutoff.isoformat()}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Retention window; defaults to MERGECHAT_RETENTION_DAYS.",
    )
    args = parser.parse_args()
    days = args.days if args.days is not None else get_settings().retention_days
    if days < 1:
        raise SystemExit("Retention days must be at least 1.")
    asyncio.run(run(days))


if __name__ == "__main__":
    main()
