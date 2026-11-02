from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mergechat.domain.message import RawMessage
from mergechat.processing.ingestion import IngestionService
from mergechat.storage import repositories


def _message(identifier: str = "1", text: str = "Need 2 horses") -> RawMessage:
    return RawMessage(
        external_message_id=identifier,
        external_chat_id="chat-1",
        chat_title="Orders",
        author_external_id="user-1",
        text=text,
        timestamp=datetime(2026, 10, 18, 14, 0, tzinfo=UTC),
    )


async def test_messages_are_deduplicated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await session.commit()
        account_id = account.id

    ingestion = IngestionService(session_factory)
    first = await ingestion.ingest(account_id, _message())
    second = await ingestion.ingest(account_id, _message())

    assert first.created is True
    assert second.created is False
    assert first.message_id == second.message_id

    async with session_factory() as session:
        messages = await repositories.list_messages(session, account_id=account_id)
        assert len(messages) == 1


async def test_edit_updates_existing_message(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await session.commit()
        account_id = account.id

    ingestion = IngestionService(session_factory)
    await ingestion.ingest(account_id, _message())
    edited = _message(text="Need 3 horses")
    edited.event_type = "edit"
    result = await ingestion.ingest(account_id, edited)

    assert result.created is False
    async with session_factory() as session:
        messages = await repositories.list_messages(session, account_id=account_id)
        assert messages[0].text == "Need 3 horses"


async def test_unlabeled_filter_and_labels(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await session.commit()
        account_id = account.id

    ingestion = IngestionService(session_factory)
    first = await ingestion.ingest(account_id, _message("1"))
    await ingestion.ingest(account_id, _message("2"))

    async with session_factory() as session:
        labels = await repositories.list_messages(
            session, account_id=account_id, unlabeled=True
        )
        assert len(labels) == 2
        record = await repositories.upsert_label(
            session, first.message_id, "order", labeler="tester"
        )
        await session.commit()
        assert record.label == "order"

    async with session_factory() as session:
        labels = await repositories.list_messages(
            session, account_id=account_id, unlabeled=True
        )
        assert len(labels) == 1


async def test_delete_event_clears_content_and_prevents_revival(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await session.commit()
        account_id = account.id

    ingestion = IngestionService(session_factory)
    result = await ingestion.ingest(account_id, _message())

    async with session_factory() as session:
        await repositories.upsert_label(session, result.message_id, "order")
        await session.commit()
    deleted = await ingestion.mark_deleted(account_id, "chat-1", ["1"])
    assert deleted == 1

    edited = _message(text="edited after delete")
    edited.event_type = "edit"
    await ingestion.ingest(account_id, edited)

    async with session_factory() as session:
        message = await repositories.get_message(session, result.message_id)
        assert message is not None
        assert message.processing_status == "deleted"
        assert message.text == ""
        assert message.attachments == []
        assert message.raw_payload == {}
        assert await repositories.list_labels(session, message_id=result.message_id) == []


async def test_claim_pending_messages_marks_rows_processing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await session.commit()
        account_id = account.id

    ingestion = IngestionService(session_factory)
    await ingestion.ingest(account_id, _message("1"))
    await ingestion.ingest(account_id, _message("2"))

    async with session_factory() as session:
        claimed = await repositories.claim_pending_messages(
            session, account_id=account_id, limit=1
        )
        await session.commit()
        assert len(claimed) == 1

    async with session_factory() as session:
        second = await repositories.claim_pending_messages(
            session, account_id=account_id, limit=10
        )
        await session.commit()
        assert len(second) == 1
        assert second[0] != claimed[0]


async def test_retention_deletes_old_messages(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await session.commit()
        account_id = account.id

    ingestion = IngestionService(session_factory)
    await ingestion.ingest(account_id, _message("old"))
    await ingestion.ingest(account_id, _message("new"))

    async with session_factory() as session:
        old = await repositories.get_message_by_external(
            session, "max", "chat-1", "old"
        )
        recent = await repositories.get_message_by_external(
            session, "max", "chat-1", "new"
        )
        assert old is not None and recent is not None
        old.received_at = datetime(2026, 10, 18, tzinfo=UTC)
        recent.received_at = datetime(2026, 11, 1, tzinfo=UTC)
        await session.commit()

    async with session_factory() as session:
        deleted = await repositories.delete_messages_before(
            session, datetime(2026, 10, 20, tzinfo=UTC)
        )
        await session.commit()
        assert deleted == 1
        remaining = await repositories.list_messages(session, account_id=account_id)
        assert [message.external_message_id for message in remaining] == ["new"]


async def test_selected_chats_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from mergechat.domain.chat import ChatInfo

    async with session_factory() as session:
        account = await repositories.create_account(session, "Owner")
        await repositories.upsert_chat(
            session,
            account.id,
            ChatInfo(external_chat_id="1", title="A"),
        )
        await repositories.upsert_chat(
            session,
            account.id,
            ChatInfo(external_chat_id="2", title="B"),
        )
        await session.commit()

        chats = await repositories.set_selected_chats(session, account.id, ["2"])
        await session.commit()
        assert [chat.selected for chat in chats] == [False, True]

        selected = await repositories.get_selected_chat_ids(session, account.id)
        assert selected == ["2"]
