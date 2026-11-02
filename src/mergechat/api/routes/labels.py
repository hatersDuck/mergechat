"""Manual labelling and import endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.api.dependencies import get_db_session
from mergechat.api.schemas import (
    LabelImportIn,
    LabelImportOut,
    LabelIn,
    LabelOut,
)
from mergechat.storage import repositories

router = APIRouter(tags=["labels"])


@router.post("/messages/{message_id}/label", response_model=LabelOut)
async def label_message(
    message_id: str,
    payload: LabelIn,
    session: AsyncSession = Depends(get_db_session),
) -> LabelOut:
    if await repositories.get_message(session, message_id) is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    record = await repositories.upsert_label(
        session,
        message_id,
        payload.label.value,
        labeler=payload.labeler,
        comment=payload.comment,
    )
    await session.commit()
    return LabelOut.from_label(record)


@router.get("/messages/{message_id}/label", response_model=list[LabelOut])
async def list_message_labels(
    message_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[LabelOut]:
    if await repositories.get_message(session, message_id) is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    labels = await repositories.list_labels(session, message_id=message_id)
    return [LabelOut.from_label(label) for label in labels]


@router.post("/labels/import", response_model=LabelImportOut)
async def import_labels(
    payload: LabelImportIn,
    session: AsyncSession = Depends(get_db_session),
) -> LabelImportOut:
    imported = 0
    skipped = 0
    for item in payload.labels:
        if await repositories.get_message(session, item.message_id) is None:
            skipped += 1
            continue
        await repositories.upsert_label(
            session,
            item.message_id,
            item.label.value,
            labeler=item.labeler,
            comment=item.comment,
        )
        imported += 1
    await session.commit()
    return LabelImportOut(imported=imported, skipped=skipped)
