"""Export messages, latest classifications and labels as JSON Lines."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mergechat.config import get_settings
from mergechat.logging import configure_logging
from mergechat.storage import repositories
from mergechat.storage.database import (
    create_engine,
    create_session_factory,
    ensure_schema,
)


async def run(account_id: str | None, output: Path, limit: int) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    await ensure_schema(settings)
    try:
        async with factory() as session:
            messages = await repositories.list_messages(
                session, account_id=account_id, limit=limit
            )
            message_ids = [message.id for message in messages]
            classifications = await repositories.get_latest_classifications(
                session, message_ids
            )
            labels_by_message = await repositories.list_labels_for_messages(
                session, message_ids
            )
            rows = []
            for message in messages:
                classification = classifications.get(message.id)
                labels = labels_by_message.get(message.id, [])
                rows.append(
                    {
                        "message": {
                            "id": message.id,
                            "account_id": message.account_id,
                            "external_chat_id": message.external_chat_id,
                            "external_message_id": message.external_message_id,
                            "author_external_id": message.author_external_id,
                            "author_name": message.author_name,
                            "text": message.text,
                            "timestamp": message.timestamp.isoformat(),
                            "attachments": message.attachments,
                            "processing_status": message.processing_status,
                        },
                        "classification": (
                            {
                                "is_order": classification.is_order,
                                "confidence": classification.confidence,
                                "attributes": classification.attributes,
                                "model": classification.model,
                                "prompt_version": classification.prompt_version,
                                "latency_ms": classification.latency_ms,
                                "usage": classification.usage,
                            }
                            if classification is not None
                            else None
                        ),
                        "labels": [
                            {
                                "label": label.label,
                                "labeler": label.labeler,
                                "comment": label.comment,
                            }
                            for label in labels
                        ],
                    }
                )
    finally:
        await engine.dispose()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id")
    parser.add_argument("--output", type=Path, default=Path("dataset.jsonl"))
    parser.add_argument("--limit", type=int, default=10000)
    args = parser.parse_args()
    asyncio.run(run(args.account_id, args.output, args.limit))


if __name__ == "__main__":
    main()
