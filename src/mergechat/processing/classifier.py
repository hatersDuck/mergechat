"""Order classification orchestration and persistence."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mergechat.domain.message import RawMessage
from mergechat.jev.schemas import JevClassification, JevResponseError
from mergechat.jev.service import JevService
from mergechat.storage import repositories
from mergechat.storage.models import Classification, ProcessingRun
from mergechat.storage.models import RawMessage as RawMessageRow

logger = logging.getLogger(__name__)


class MessageNotFoundError(LookupError):
    """Raised when a message id does not exist."""


class MessageDeletedError(LookupError):
    """Raised when a message was deleted and cannot be classified."""


class MessageBusyError(RuntimeError):
    """Raised when another worker has already claimed a message."""


@dataclass(slots=True)
class BatchClassificationResult:
    processed: int = 0
    failed: int = 0
    run_id: str | None = None


def message_to_dto(row: RawMessageRow) -> RawMessage:
    return RawMessage(
        platform=row.platform,
        external_message_id=row.external_message_id,
        external_chat_id=row.external_chat_id,
        chat_title=None,
        author_external_id=row.author_external_id,
        author_name=row.author_name,
        text=row.text,
        timestamp=row.timestamp,
        attachments=row.attachments or [],
        raw_payload=row.raw_payload or {},
    )


class ClassifierService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        jev_service: JevService | None,
    ) -> None:
        self._session_factory = session_factory
        self._jev = jev_service

    async def classify_message(self, message_id: str) -> Classification:
        return await self._classify_message(message_id, allow_processing=False)

    async def _classify_message(
        self, message_id: str, *, allow_processing: bool
    ) -> Classification:
        jev = self._jev
        if jev is None:
            raise JevResponseError(
                "JEV is not configured. Set MERGECHAT_JEV_API_KEY."
            )
        async with self._session_factory() as session:
            row = await repositories.get_message(session, message_id)
            if row is None:
                raise MessageNotFoundError(message_id)
            if row.processing_status == "deleted":
                raise MessageDeletedError(message_id)
            if row.processing_status == "processing" and not allow_processing:
                raise MessageBusyError(message_id)
            dto = message_to_dto(row)

        try:
            result = await jev.classify(dto)
        except Exception as exc:
            async with self._session_factory() as session:
                row = await repositories.get_message(session, message_id)
                if row is not None and row.processing_status != "deleted":
                    await repositories.create_classification(
                        session,
                        message_id,
                        provider="jev",
                        model=None,
                        prompt_version=jev.prompt_version,
                        status="failed",
                        error=str(exc),
                    )
                    await repositories.set_message_processing_status(
                        session, row, "failed", str(exc)
                    )
                await session.commit()
            logger.exception(
                "JEV classification failed",
                extra={"message_id": message_id},
            )
            raise

        return await self._persist_success(message_id, result)

    async def _persist_success(
        self, message_id: str, result: JevClassification
    ) -> Classification:
        async with self._session_factory() as session:
            row = await repositories.get_message(session, message_id)
            if row is None:
                raise MessageNotFoundError(message_id)
            if row.processing_status == "deleted":
                raise MessageDeletedError(message_id)
            record = await repositories.create_classification(
                session,
                message_id,
                provider="jev",
                model=result.model,
                prompt_version=result.prompt_version,
                status="ok",
                is_order=result.is_order,
                confidence=result.confidence,
                attributes=result.attributes,
                answers=result.answers,
                usage=result.usage,
                latency_ms=result.latency_ms,
            )
            await repositories.set_message_processing_status(
                session, row, "classified"
            )
            await session.commit()
        logger.info(
            "message classified",
            extra={
                "message_id": message_id,
                "is_order": result.is_order,
                "confidence": result.confidence,
                "latency_ms": result.latency_ms,
            },
        )
        return record

    async def classify_pending(
        self,
        *,
        account_id: str | None = None,
        limit: int = 50,
    ) -> BatchClassificationResult:
        async with self._session_factory() as session:
            await repositories.reset_stale_processing(session)
            message_ids = await repositories.claim_pending_messages(
                session, account_id=account_id, limit=limit
            )
            run = await repositories.create_processing_run(session, "classification")
            await session.commit()
            run_id = run.id

        semaphore = asyncio.Semaphore(3)

        async def classify_one(message_id: str) -> bool:
            async with semaphore:
                try:
                    await self._classify_message(
                        message_id, allow_processing=True
                    )
                    return True
                except Exception:
                    logger.exception(
                        "batch classification failed",
                        extra={"message_id": message_id},
                    )
                    return False

        results = await asyncio.gather(
            *(classify_one(message_id) for message_id in message_ids)
        )
        processed = sum(1 for result in results if result)
        failed = len(results) - processed

        async with self._session_factory() as session:
            run_record = await session.get(ProcessingRun, run_id)
            if run_record is not None:
                await repositories.finish_processing_run(
                    session,
                    run_record,
                    status="completed" if failed == 0 else "completed_with_errors",
                    processed_count=processed,
                    error_count=failed,
                )
            await session.commit()
        return BatchClassificationResult(
            processed=processed, failed=failed, run_id=run_id
        )
