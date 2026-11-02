"""SQLAlchemy models for the Phase 0 schema."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class AccountSession(Base):
    __tablename__ = "account_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(32), default="max", index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    encrypted_session_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "external_chat_id", name="uq_chat_account_external"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("account_sessions.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32), default="max")
    external_chat_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    chat_type: Mapped[str] = mapped_column(String(32), default="CHAT")
    participants_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_count: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RawMessage(Base):
    __tablename__ = "raw_messages"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_chat_id",
            "external_message_id",
            name="uq_message_platform_chat_external",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("account_sessions.id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="SET NULL"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32), default="max")
    external_message_id: Mapped[str] = mapped_column(String(128))
    external_chat_id: Mapped[str] = mapped_column(String(128), index=True)
    author_external_id: Mapped[str | None] = mapped_column(String(128))
    author_name: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    processing_status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_messages.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="jev")
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    is_order: Mapped[bool | None] = mapped_column(Boolean, index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    route_from: Mapped[str | None] = mapped_column(String(255))
    route_to: Mapped[str | None] = mapped_column(String(255))
    travel_date: Mapped[str | None] = mapped_column(String(64))
    cargo_type: Mapped[str | None] = mapped_column(String(64))
    price: Mapped[str | None] = mapped_column(String(128))
    contact: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManualLabel(Base):
    __tablename__ = "manual_labels"
    __table_args__ = (
        UniqueConstraint("message_id", "labeler", name="uq_label_message_labeler"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_messages.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(32), index=True)
    labeler: Mapped[str] = mapped_column(String(128), default="local")
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    run_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
