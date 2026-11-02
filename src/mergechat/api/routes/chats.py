"""Chat discovery and selection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.api.dependencies import get_db_session, get_registry
from mergechat.api.schemas import ChatOut, ChatSelectionIn, ChatSelectionOut
from mergechat.connectors.registry import ConnectorRegistry
from mergechat.storage import repositories

router = APIRouter(tags=["chats"])


async def _require_account(session: AsyncSession, account_id: str) -> None:
    if await repositories.get_account(session, account_id) is None:
        raise HTTPException(status_code=404, detail="Account not found.")


@router.get("/accounts/{account_id}/chats", response_model=list[ChatOut])
async def list_chats(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> list[ChatOut]:
    await _require_account(session, account_id)
    connector = registry.get(account_id)
    if connector is not None:
        try:
            await registry.list_chats(account_id)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Could not refresh Max chats: {exc}"
            ) from exc
        await session.commit()
    chats = await repositories.list_chats(session, account_id)
    return [ChatOut.from_chat(chat) for chat in chats]


@router.post(
    "/accounts/{account_id}/chats/selection",
    response_model=ChatSelectionOut,
)
async def select_chats(
    account_id: str,
    payload: ChatSelectionIn,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> ChatSelectionOut:
    await _require_account(session, account_id)
    existing = await repositories.list_chats(session, account_id)
    known = {chat.external_chat_id for chat in existing}
    unknown = sorted(set(payload.chat_ids) - known)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"unknown_chat_ids": unknown},
        )
    if not existing:
        raise HTTPException(
            status_code=409,
            detail="Connect the account and refresh chats before selecting.",
        )

    chats = await repositories.set_selected_chats(
        session, account_id, payload.chat_ids
    )
    await session.commit()
    await registry.subscribe(account_id, payload.chat_ids)
    selected = [chat.external_chat_id for chat in chats if chat.selected]
    return ChatSelectionOut(
        account_id=account_id,
        selected_chat_ids=selected,
        chats=[ChatOut.from_chat(chat) for chat in chats],
    )
