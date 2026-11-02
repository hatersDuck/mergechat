"""Classification runs, export and evaluation metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.api.dependencies import get_classifier, get_db_session
from mergechat.api.schemas import (
    ClassificationOut,
    ClassificationRunIn,
    ClassificationRunOut,
    ExportRow,
    MessageOut,
    MetricsOut,
)
from mergechat.processing.classifier import ClassifierService
from mergechat.processing.metrics import quality_metrics
from mergechat.storage import repositories

router = APIRouter(tags=["classifications"])


@router.post("/classifications/run", response_model=ClassificationRunOut)
async def run_classification(
    payload: ClassificationRunIn,
    classifier: ClassifierService = Depends(get_classifier),
) -> ClassificationRunOut:
    result = await classifier.classify_pending(
        account_id=payload.account_id, limit=payload.limit
    )
    return ClassificationRunOut(
        processed=result.processed,
        failed=result.failed,
        run_id=result.run_id,
    )


@router.get("/classifications/export", response_model=list[ExportRow])
async def export_classifications(
    account_id: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[ExportRow]:
    rows = await repositories.list_classifications(
        session, account_id=account_id, limit=limit, offset=offset
    )
    return [
        ExportRow(
            message=MessageOut.from_message(message),
            classification=ClassificationOut.from_classification(classification),
        )
        for classification, message in rows
    ]


@router.get("/classifications/metrics", response_model=MetricsOut)
async def classification_metrics(
    account_id: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> MetricsOut:
    metrics = await repositories.get_metrics(session, account_id)
    quality = await quality_metrics(session, account_id=account_id)
    return MetricsOut(
        account_id=account_id,
        messages=int(metrics["messages"]),
        classified_messages=int(metrics["classified_messages"]),
        pending_messages=int(metrics["pending_messages"]),
        manual_labels=int(metrics["manual_labels"]),
        order_predictions=int(metrics["order_predictions"]),
        average_jev_latency_ms=metrics["average_jev_latency_ms"],  # type: ignore[arg-type]
        quality=quality,
    )
