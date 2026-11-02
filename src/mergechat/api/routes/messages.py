"""Stored message and single-message classification endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.api.dependencies import get_classifier, get_db_session
from mergechat.api.schemas import ClassificationOut, MessageOut
from mergechat.jev.schemas import JevResponseError
from mergechat.processing.classifier import (
    ClassifierService,
    MessageBusyError,
    MessageDeletedError,
    MessageNotFoundError,
)
from mergechat.storage import repositories

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messages"])


@router.get("/messages", response_model=list[MessageOut])
async def list_messages(
    account_id: str | None = None,
    unlabeled: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[MessageOut]:
    messages = await repositories.list_messages(
        session,
        account_id=account_id,
        unlabeled=unlabeled,
        limit=limit,
        offset=offset,
    )
    return [MessageOut.from_message(message) for message in messages]


@router.get("/messages/{message_id}", response_model=MessageOut)
async def get_message(
    message_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> MessageOut:
    message = await repositories.get_message(session, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    if message.processing_status == "deleted":
        raise HTTPException(status_code=410, detail="Message was deleted.")
    return MessageOut.from_message(message)


@router.get(
    "/messages/{message_id}/classification",
    response_model=ClassificationOut,
)
async def get_message_classification(
    message_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ClassificationOut:
    message = await repositories.get_message(session, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    if message.processing_status == "deleted":
        raise HTTPException(status_code=410, detail="Message was deleted.")
    record = await repositories.get_latest_classification(session, message_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No classification yet.")
    return ClassificationOut.from_classification(record)


@router.post(
    "/messages/{message_id}/classify",
    response_model=ClassificationOut,
)
async def classify_message(
    message_id: str,
    classifier: ClassifierService = Depends(get_classifier),
) -> ClassificationOut:
    try:
        record = await classifier.classify_message(message_id)
    except MessageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Message not found.") from exc
    except MessageDeletedError as exc:
        raise HTTPException(status_code=410, detail="Message was deleted.") from exc
    except MessageBusyError as exc:
        raise HTTPException(
            status_code=409, detail="Message is already being classified."
        ) from exc
    except JevResponseError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("classification request failed", extra={"message_id": message_id})
        raise HTTPException(
            status_code=502, detail=f"JEV classification failed: {exc}"
        ) from exc
    return ClassificationOut.from_classification(record)
