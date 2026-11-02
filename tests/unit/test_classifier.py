from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mergechat.domain.message import RawMessage
from mergechat.jev.schemas import JevClassification
from mergechat.processing.classifier import ClassifierService
from mergechat.processing.ingestion import IngestionService
from mergechat.processing.metrics import quality_metrics
from mergechat.storage import repositories


class FakeJev:
    prompt_version = "fake-v1"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def classify(self, message: RawMessage) -> JevClassification:
        if self.fail:
            raise RuntimeError("JEV unavailable")
        return JevClassification(
            is_order=True,
            confidence=0.92,
            answers={"is_order": {"type": "noul", "noul": 0.92}},
            attributes={"animal_type": "horses", "cargo_type": "horse"},
            model="fake-model",
            usage={"input_tokens": 10, "output_tokens": 2},
            latency_ms=12.5,
            prompt_version=self.prompt_version,
        )


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await session.commit()
        account_id = account.id
    message = RawMessage(
        external_message_id="1",
        external_chat_id="chat-1",
        text="Need 2 horses",
        timestamp=datetime(2026, 10, 18, tzinfo=UTC),
    )
    result = await IngestionService(session_factory).ingest(account_id, message)
    return result.message_id


async def test_classification_is_persisted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    message_id = await _seed(session_factory)
    classifier = ClassifierService(session_factory, FakeJev())  # type: ignore[arg-type]

    record = await classifier.classify_message(message_id)

    assert record.is_order is True
    assert record.confidence == pytest.approx(0.92)
    assert record.attributes["animal_type"] == "horses"

    async with session_factory() as session:
        message = await repositories.get_message(session, message_id)
        assert message is not None
        assert message.processing_status == "classified"
        metrics = await repositories.get_metrics(session)
        assert metrics["order_predictions"] == 1

        await repositories.upsert_label(session, message_id, "order", labeler="tester")
        await session.commit()
        quality = await quality_metrics(session)
        assert quality["true_positives"] == 1
        assert quality["precision"] == pytest.approx(1.0)
        assert quality["recall"] == pytest.approx(1.0)


async def test_failed_classification_is_recorded(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    message_id = await _seed(session_factory)
    classifier = ClassifierService(
        session_factory, FakeJev(fail=True)  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError):
        await classifier.classify_message(message_id)

    async with session_factory() as session:
        message = await repositories.get_message(session, message_id)
        assert message is not None
        assert message.processing_status == "failed"
        latest = await repositories.get_latest_classification(session, message_id)
        assert latest is not None
        assert latest.status == "failed"
        assert "JEV unavailable" in (latest.error or "")
