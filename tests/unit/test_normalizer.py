from __future__ import annotations

from pymax import Chat, Message

from mergechat.connectors.max.normalizer import normalize_message


def test_normalizes_message_and_millisecond_timestamp() -> None:
    chat = Chat(
        id=555,
        type="CHAT",
        status="ACTIVE",
        owner=1,
        title="Horse logistics",
        participants_count=12,
        messages_count=100,
    )
    message = Message(
        id=10,
        chat_id=555,
        sender=42,
        text="Need 2 horses Moscow -> Tver",
        time=1_779_805_553_478,
        type="TEXT",
    )

    raw = normalize_message(message, chat=chat)

    assert raw is not None
    assert raw.external_chat_id == "555"
    assert raw.external_message_id == "10"
    assert raw.chat_title == "Horse logistics"
    assert raw.author_external_id == "42"
    assert raw.text == "Need 2 horses Moscow -> Tver"
    assert raw.timestamp.year == 2026
    assert raw.raw_payload["id"] == 10


def test_skips_message_without_chat_id() -> None:
    message = Message(id=10, sender=42, text="orphan", time=1, type="TEXT")
    assert normalize_message(message) is None
