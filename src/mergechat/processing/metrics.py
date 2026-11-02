"""Quality and operational metrics for the spike report."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.storage.models import Classification, ManualLabel, RawMessage


async def quality_metrics(
    session: AsyncSession,
    *,
    account_id: str | None = None,
) -> dict[str, float | int | None]:
    """Compute precision/recall from manual labels and latest predictions."""

    latest = (
        select(
            Classification.message_id.label("message_id"),
            Classification.is_order.label("is_order"),
            func.row_number()
            .over(
                partition_by=Classification.message_id,
                order_by=Classification.created_at.desc(),
            )
            .label("rank"),
        )
        .subquery()
    )
    stmt = (
        select(ManualLabel.label, latest.c.is_order)
        .join(RawMessage, ManualLabel.message_id == RawMessage.id)
        .join(latest, latest.c.message_id == ManualLabel.message_id)
        .where(
            latest.c.rank == 1,
            RawMessage.processing_status != "deleted",
        )
    )
    if account_id:
        stmt = stmt.where(RawMessage.account_id == account_id)
    result = await session.execute(stmt)

    tp = fp = fn = tn = 0
    labelled_messages = 0
    for truth, predicted in result.all():
        if truth == "uncertain" or predicted is None:
            continue
        labelled_messages += 1
        is_order = bool(predicted)
        if truth == "order" and is_order:
            tp += 1
        elif truth == "order" and not is_order:
            fn += 1
        elif truth == "not_order" and is_order:
            fp += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "precision": precision,
        "recall": recall,
        "labelled_messages": labelled_messages,
    }
