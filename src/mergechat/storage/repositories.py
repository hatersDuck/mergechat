"""Database access helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.domain.chat import ChatInfo
from mergechat.domain.message import RawMessage as RawMessageDTO
from mergechat.storage.models import (
    AccountSession,
    Chat,
    Classification,
    ManualLabel,
    ProcessingRun,
    RawMessage,
)


async def create_account(
    session: AsyncSession,
    display_name: str,
    platform: str = "max",
) -> AccountSession:
    account = AccountSession(display_name=display_name, platform=platform)
    session.add(account)
    await session.flush()
    return account


async def get_account(session: AsyncSession, account_id: str) -> AccountSession | None:
    return await session.get(AccountSession, account_id)


async def list_accounts(session: AsyncSession) -> list[AccountSession]:
    result = await session.scalars(select(AccountSession).order_by(AccountSession.created_at))
    return list(result)


async def update_account_status(
    session: AsyncSession,
    account: AccountSession,
    status: str,
    *,
    error: str | None = None,
    health_check: bool = False,
) -> AccountSession:
    account.status = status
    account.last_error = error
    if health_check:
        account.last_health_check = datetime.now(UTC)
    await session.flush()
    return account


async def set_encrypted_session(
    session: AsyncSession,
    account: AccountSession,
    encrypted_session_data: bytes | None,
) -> None:
    account.encrypted_session_data = encrypted_session_data
    await session.flush()


async def upsert_chat(
    session: AsyncSession,
    account_id: str,
    info: ChatInfo,
    platform: str = "max",
) -> Chat:
    chat = await session.scalar(
        select(Chat).where(
            Chat.account_id == account_id,
            Chat.external_chat_id == info.external_chat_id,
        )
    )
    if chat is None:
        chat = Chat(
            account_id=account_id,
            platform=platform,
            external_chat_id=info.external_chat_id,
            title=info.title,
            chat_type=info.chat_type,
            participants_count=info.participants_count,
            messages_count=info.messages_count,
            selected=info.selected,
        )
        session.add(chat)
    else:
        chat.title = info.title
        chat.chat_type = info.chat_type
        chat.participants_count = info.participants_count
        chat.messages_count = info.messages_count
    await session.flush()
    return chat


async def list_chats(session: AsyncSession, account_id: str) -> list[Chat]:
    result = await session.scalars(
        select(Chat)
        .where(Chat.account_id == account_id)
        .order_by(Chat.selected.desc(), Chat.title)
    )
    return list(result)


async def get_selected_chat_ids(session: AsyncSession, account_id: str) -> list[str]:
    result = await session.scalars(
        select(Chat.external_chat_id).where(
            Chat.account_id == account_id, Chat.selected.is_(True)
        )
    )
    return list(result)


async def set_selected_chats(
    session: AsyncSession,
    account_id: str,
    external_chat_ids: Sequence[str],
) -> list[Chat]:
    wanted = set(external_chat_ids)
    chats = await list_chats(session, account_id)
    for chat in chats:
        chat.selected = chat.external_chat_id in wanted
    await session.flush()
    return chats


async def get_or_create_chat(
    session: AsyncSession,
    account_id: str,
    external_chat_id: str,
    *,
    title: str | None = None,
    platform: str = "max",
) -> Chat:
    chat = await session.scalar(
        select(Chat).where(
            Chat.account_id == account_id,
            Chat.external_chat_id == external_chat_id,
        )
    )
    if chat is None:
        chat = Chat(
            account_id=account_id,
            platform=platform,
            external_chat_id=external_chat_id,
            title=title,
        )
        session.add(chat)
        await session.flush()
    elif title and not chat.title:
        chat.title = title
    return chat


async def message_exists(
    session: AsyncSession,
    platform: str,
    external_chat_id: str,
    external_message_id: str,
) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    RawMessage.platform == platform,
                    RawMessage.external_chat_id == external_chat_id,
                    RawMessage.external_message_id == external_message_id,
                )
            )
        )
    )


async def get_message(session: AsyncSession, message_id: str) -> RawMessage | None:
    return await session.get(RawMessage, message_id)


async def get_message_by_external(
    session: AsyncSession,
    platform: str,
    external_chat_id: str,
    external_message_id: str,
) -> RawMessage | None:
    return await session.scalar(
        select(RawMessage).where(
            RawMessage.platform == platform,
            RawMessage.external_chat_id == external_chat_id,
            RawMessage.external_message_id == external_message_id,
        )
    )


async def insert_message(
    session: AsyncSession,
    account_id: str,
    message: RawMessageDTO,
) -> tuple[RawMessage, bool]:
    existing = await get_message_by_external(
        session,
        message.platform,
        message.external_chat_id,
        message.external_message_id,
    )
    if existing is not None:
        if message.event_type == "edit" and existing.processing_status != "deleted":
            existing.text = message.text
            existing.attachments = message.attachments
            existing.raw_payload = message.raw_payload
            existing.processing_status = "pending"
            existing.processing_error = None
            await session.flush()
        return existing, False

    chat = await get_or_create_chat(
        session,
        account_id,
        message.external_chat_id,
        title=message.chat_title,
        platform=message.platform,
    )
    row = RawMessage(
        account_id=account_id,
        chat_id=chat.id,
        platform=message.platform,
        external_message_id=message.external_message_id,
        external_chat_id=message.external_chat_id,
        author_external_id=message.author_external_id,
        author_name=message.author_name,
        text=message.text,
        timestamp=message.timestamp,
        attachments=message.attachments,
        raw_payload=message.raw_payload,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await get_message_by_external(
            session,
            message.platform,
            message.external_chat_id,
            message.external_message_id,
        )
        if existing is None:
            raise
        return existing, False
    return row, True


async def mark_messages_deleted(
    session: AsyncSession,
    account_id: str,
    external_chat_id: str,
    external_message_ids: Sequence[str],
) -> int:
    if not external_message_ids:
        return 0
    result = await session.scalars(
        select(RawMessage).where(
            RawMessage.account_id == account_id,
            RawMessage.external_chat_id == external_chat_id,
            RawMessage.external_message_id.in_(list(external_message_ids)),
        )
    )
    messages = list(result)
    message_ids = [message.id for message in messages]
    if message_ids:
        await session.execute(
            delete(Classification).where(Classification.message_id.in_(message_ids))
        )
        await session.execute(
            delete(ManualLabel).where(ManualLabel.message_id.in_(message_ids))
        )
    for message in messages:
        message.processing_status = "deleted"
        message.processing_error = None
        message.text = ""
        message.attachments = []
        message.raw_payload = {}
    await session.flush()
    return len(messages)


async def list_messages(
    session: AsyncSession,
    *,
    account_id: str | None = None,
    unlabeled: bool = False,
    limit: int = 100,
    offset: int = 0,
    include_deleted: bool = False,
) -> list[RawMessage]:
    stmt = select(RawMessage)
    if account_id:
        stmt = stmt.where(RawMessage.account_id == account_id)
    if not include_deleted:
        stmt = stmt.where(RawMessage.processing_status != "deleted")
    if unlabeled:
        stmt = stmt.where(
            ~exists().where(ManualLabel.message_id == RawMessage.id)
        )
    stmt = stmt.order_by(RawMessage.timestamp.desc()).limit(limit).offset(offset)
    result = await session.scalars(stmt)
    return list(result)


async def list_pending_messages(
    session: AsyncSession,
    *,
    account_id: str | None = None,
    limit: int = 50,
) -> list[RawMessage]:
    stmt = select(RawMessage).where(RawMessage.processing_status == "pending")
    if account_id:
        stmt = stmt.where(RawMessage.account_id == account_id)
    stmt = stmt.order_by(RawMessage.timestamp).limit(limit)
    result = await session.scalars(stmt)
    return list(result)


async def claim_pending_messages(
    session: AsyncSession,
    *,
    account_id: str | None = None,
    limit: int = 50,
) -> list[str]:
    """Atomically claim pending messages for one classification worker."""
    stmt = select(RawMessage.id).where(RawMessage.processing_status == "pending")
    if account_id:
        stmt = stmt.where(RawMessage.account_id == account_id)
    stmt = stmt.order_by(RawMessage.timestamp).limit(limit)
    candidates = list(await session.scalars(stmt))
    if not candidates:
        return []

    result = await session.execute(
        update(RawMessage)
        .where(
            RawMessage.id.in_(candidates),
            RawMessage.processing_status == "pending",
        )
        .values(processing_status="processing")
        .returning(RawMessage.id)
    )
    claimed = [row[0] for row in result]
    await session.flush()
    return claimed


async def reset_stale_processing(
    session: AsyncSession, *, older_than_minutes: int = 15
) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    result = await session.execute(
        update(RawMessage)
        .where(
            RawMessage.processing_status == "processing",
            RawMessage.updated_at < cutoff,
        )
        .values(processing_status="pending", processing_error="stale claim reset")
    )
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


async def set_message_processing_status(
    session: AsyncSession,
    message: RawMessage,
    status: str,
    error: str | None = None,
) -> None:
    message.processing_status = status
    message.processing_error = error
    await session.flush()


async def create_classification(
    session: AsyncSession,
    message_id: str,
    *,
    provider: str,
    model: str | None,
    prompt_version: str,
    status: str,
    is_order: bool | None = None,
    confidence: float | None = None,
    keywords: Sequence[str] = (),
    attributes: dict | None = None,
    answers: dict | None = None,
    usage: dict | None = None,
    latency_ms: float | None = None,
    error: str | None = None,
) -> Classification:
    attributes = attributes or {}
    record = Classification(
        message_id=message_id,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        status=status,
        is_order=is_order,
        confidence=confidence,
        keywords=list(keywords),
        route_from=attributes.get("route_from"),
        route_to=attributes.get("route_to"),
        travel_date=attributes.get("date"),
        cargo_type=attributes.get("cargo_type"),
        price=attributes.get("price"),
        contact=attributes.get("contact"),
        reason=attributes.get("reason"),
        attributes=attributes,
        answers=answers or {},
        usage=usage or {},
        latency_ms=latency_ms,
        error=error,
    )
    session.add(record)
    await session.flush()
    return record


async def get_latest_classification(
    session: AsyncSession, message_id: str
) -> Classification | None:
    return await session.scalar(
        select(Classification)
        .where(Classification.message_id == message_id)
        .order_by(Classification.created_at.desc())
        .limit(1)
    )


async def get_latest_classifications(
    session: AsyncSession, message_ids: Sequence[str]
) -> dict[str, Classification]:
    if not message_ids:
        return {}
    result = await session.scalars(
        select(Classification)
        .where(Classification.message_id.in_(list(message_ids)))
        .order_by(Classification.created_at.desc())
    )
    latest: dict[str, Classification] = {}
    for classification in result:
        latest.setdefault(classification.message_id, classification)
    return latest


async def list_labels_for_messages(
    session: AsyncSession, message_ids: Sequence[str]
) -> dict[str, list[ManualLabel]]:
    if not message_ids:
        return {}
    result = await session.scalars(
        select(ManualLabel)
        .where(ManualLabel.message_id.in_(list(message_ids)))
        .order_by(ManualLabel.created_at.desc())
    )
    labels: dict[str, list[ManualLabel]] = {}
    for label in result:
        labels.setdefault(label.message_id, []).append(label)
    return labels


async def list_classifications(
    session: AsyncSession,
    *,
    account_id: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[tuple[Classification, RawMessage]]:
    stmt = (
        select(Classification, RawMessage)
        .join(RawMessage, Classification.message_id == RawMessage.id)
        .where(RawMessage.processing_status != "deleted")
        .order_by(Classification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if account_id:
        stmt = stmt.where(RawMessage.account_id == account_id)
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def upsert_label(
    session: AsyncSession,
    message_id: str,
    label: str,
    labeler: str = "local",
    comment: str | None = None,
) -> ManualLabel:
    record = await session.scalar(
        select(ManualLabel).where(
            ManualLabel.message_id == message_id,
            ManualLabel.labeler == labeler,
        )
    )
    if record is None:
        record = ManualLabel(
            message_id=message_id,
            label=label,
            labeler=labeler,
            comment=comment,
        )
        session.add(record)
    else:
        record.label = label
        record.comment = comment
    await session.flush()
    return record


async def list_labels(
    session: AsyncSession,
    *,
    message_id: str | None = None,
    limit: int = 500,
) -> list[ManualLabel]:
    stmt = select(ManualLabel).order_by(ManualLabel.created_at.desc()).limit(limit)
    if message_id:
        stmt = stmt.where(ManualLabel.message_id == message_id)
    result = await session.scalars(stmt)
    return list(result)


async def get_metrics(
    session: AsyncSession, account_id: str | None = None
) -> dict[str, Any]:
    message_filter = [RawMessage.processing_status != "deleted"]
    if account_id:
        message_filter.append(RawMessage.account_id == account_id)

    total_messages = await session.scalar(
        select(func.count()).select_from(RawMessage).where(*message_filter)
    )
    classified = await session.scalar(
        select(func.count())
        .select_from(RawMessage)
        .where(*message_filter, RawMessage.processing_status == "classified")
    )
    pending = await session.scalar(
        select(func.count())
        .select_from(RawMessage)
        .where(*message_filter, RawMessage.processing_status.in_(("pending", "failed")))
    )
    labels = await session.scalar(
        select(func.count())
        .select_from(ManualLabel)
        .join(RawMessage, ManualLabel.message_id == RawMessage.id)
        .where(*message_filter)
    )
    orders = await session.scalar(
        select(func.count())
        .select_from(Classification)
        .join(RawMessage, Classification.message_id == RawMessage.id)
        .where(*message_filter, Classification.is_order.is_(True))
    )
    avg_latency = await session.scalar(
        select(func.avg(Classification.latency_ms))
        .select_from(Classification)
        .join(RawMessage, Classification.message_id == RawMessage.id)
        .where(*message_filter, Classification.latency_ms.is_not(None))
    )
    return {
        "messages": int(total_messages or 0),
        "classified_messages": int(classified or 0),
        "pending_messages": int(pending or 0),
        "manual_labels": int(labels or 0),
        "order_predictions": int(orders or 0),
        "average_jev_latency_ms": float(avg_latency) if avg_latency is not None else None,
    }


async def reset_transient_account_statuses(session: AsyncSession) -> int:
    """Mark non-terminal account states as disconnected after a restart."""
    result = await session.execute(
        update(AccountSession)
        .where(
            AccountSession.status.in_(
                ("connecting", "pending_auth", "connected", "reconnecting")
            )
        )
        .values(status="disconnected")
    )
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


async def delete_account(session: AsyncSession, account_id: str) -> bool:
    """Delete an account and all dependent rows."""
    account = await session.get(AccountSession, account_id)
    if account is None:
        return False
    message_ids = select(RawMessage.id).where(RawMessage.account_id == account_id)
    await session.execute(
        delete(Classification).where(Classification.message_id.in_(message_ids))
    )
    await session.execute(
        delete(ManualLabel).where(ManualLabel.message_id.in_(message_ids))
    )
    await session.execute(delete(RawMessage).where(RawMessage.account_id == account_id))
    await session.execute(delete(Chat).where(Chat.account_id == account_id))
    await session.delete(account)
    await session.flush()
    return True


async def clear_account_session(
    session: AsyncSession, account_id: str
) -> AccountSession | None:
    account = await session.get(AccountSession, account_id)
    if account is None:
        return None
    account.encrypted_session_data = None
    account.status = "created"
    account.last_error = None
    await session.flush()
    return account


async def delete_messages_before(session: AsyncSession, cutoff: datetime) -> int:
    """Delete messages received before ``cutoff`` and their dependent rows."""
    message_ids = select(RawMessage.id).where(RawMessage.received_at < cutoff)
    await session.execute(
        delete(Classification).where(Classification.message_id.in_(message_ids))
    )
    await session.execute(
        delete(ManualLabel).where(ManualLabel.message_id.in_(message_ids))
    )
    result = await session.execute(
        delete(RawMessage).where(RawMessage.received_at < cutoff)
    )
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


async def create_processing_run(session: AsyncSession, kind: str) -> ProcessingRun:
    run = ProcessingRun(kind=kind)
    session.add(run)
    await session.flush()
    return run


async def finish_processing_run(
    session: AsyncSession,
    run: ProcessingRun,
    *,
    status: str,
    processed_count: int,
    error_count: int,
    error: str | None = None,
    metadata: dict | None = None,
) -> None:
    run.status = status
    run.processed_count = processed_count
    run.error_count = error_count
    run.error = error
    run.run_metadata = metadata or {}
    run.finished_at = datetime.now(UTC)
    await session.flush()
