"""Account creation, connection and listener endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.api.dependencies import get_db_session, get_registry
from mergechat.api.schemas import (
    AccountCreate,
    AccountOut,
    AccountStatusOut,
    ConnectOut,
    HealthOut,
)
from mergechat.connectors.registry import AccountNotFoundError, ConnectorRegistry
from mergechat.storage import repositories

router = APIRouter(tags=["accounts"])


async def _require_account(session: AsyncSession, account_id: str):
    account = await repositories.get_account(session, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_db_session),
) -> AccountOut:
    account = await repositories.create_account(
        session, payload.display_name, payload.platform
    )
    await session.commit()
    return AccountOut.from_account(account)


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    session: AsyncSession = Depends(get_db_session),
) -> list[AccountOut]:
    accounts = await repositories.list_accounts(session)
    return [AccountOut.from_account(account) for account in accounts]


@router.post("/accounts/{account_id}/connect", response_model=ConnectOut)
async def connect_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> ConnectOut:
    await _require_account(session, account_id)
    try:
        result = await registry.connect(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Account not found.") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Max connection failed: {exc}"
        ) from exc
    return ConnectOut(
        account_id=result.account_id,
        status=result.status,
        connected=result.connected,
        qr_link=result.qr_link,
    )


@router.get("/accounts/{account_id}/status", response_model=AccountStatusOut)
async def account_status(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> AccountStatusOut:
    account = await _require_account(session, account_id)
    health = await registry.health(account_id)
    connector = registry.get(account_id)
    qr_link = None
    if connector is not None and not health.connected:
        qr_link = connector.qr_link
    reported_status = account.status
    if connector is None and reported_status in {
        "connecting",
        "pending_auth",
        "connected",
        "reconnecting",
    }:
        reported_status = "disconnected"
    return AccountStatusOut(
        account_id=account_id,
        status=reported_status,
        connected=health.connected,
        qr_link=qr_link,
        last_message_at=account.last_message_at,
        reconnect_count=health.reconnect_count,
        error=health.error,
    )


@router.get("/accounts/{account_id}/health", response_model=HealthOut)
async def account_health(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> HealthOut:
    await _require_account(session, account_id)
    health = await registry.health(account_id)
    return HealthOut(
        account_id=account_id,
        connected=health.connected,
        status=health.status,
        last_event_at=health.last_event_at,
        reconnect_count=health.reconnect_count,
        error=health.error,
    )


@router.post("/accounts/{account_id}/listener/start", response_model=ConnectOut)
async def start_listener(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> ConnectOut:
    await _require_account(session, account_id)
    try:
        result = await registry.start_listener(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Max listener failed to start: {exc}"
        ) from exc
    return ConnectOut(
        account_id=result.account_id,
        status=result.status,
        connected=result.connected,
        qr_link=result.qr_link,
    )


@router.post("/accounts/{account_id}/listener/stop", status_code=204)
async def stop_listener(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> None:
    await _require_account(session, account_id)
    await registry.stop_listener(account_id)


@router.post("/accounts/{account_id}/disconnect", status_code=204)
async def disconnect_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> None:
    await _require_account(session, account_id)
    await registry.disconnect(account_id)


@router.delete("/accounts/{account_id}/session", status_code=204)
async def revoke_session(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> None:
    await _require_account(session, account_id)
    await registry.revoke_session(account_id)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    registry: ConnectorRegistry = Depends(get_registry),
) -> None:
    await _require_account(session, account_id)
    await registry.delete_account(account_id)
