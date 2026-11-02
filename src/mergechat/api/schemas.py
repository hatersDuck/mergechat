"""API request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mergechat.domain.label import LabelValue
from mergechat.storage.models import (
    AccountSession,
    Chat,
    Classification,
    ManualLabel,
    RawMessage,
)


class AccountCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    platform: Literal["max"] = "max"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    display_name: str
    status: str
    has_session: bool
    last_health_check: datetime | None
    last_message_at: datetime | None
    reconnect_count: int
    last_error: str | None
    created_at: datetime

    @classmethod
    def from_account(cls, account: AccountSession) -> AccountOut:
        return cls(
            id=account.id,
            platform=account.platform,
            display_name=account.display_name,
            status=account.status,
            has_session=bool(account.encrypted_session_data),
            last_health_check=account.last_health_check,
            last_message_at=account.last_message_at,
            reconnect_count=account.reconnect_count,
            last_error=account.last_error,
            created_at=account.created_at,
        )


class ConnectOut(BaseModel):
    account_id: str
    status: str
    connected: bool
    qr_link: str | None = None


class AccountStatusOut(BaseModel):
    account_id: str
    status: str
    connected: bool
    qr_link: str | None = None
    last_message_at: datetime | None = None
    reconnect_count: int = 0
    error: str | None = None


class HealthOut(BaseModel):
    account_id: str
    connected: bool
    status: str
    last_event_at: datetime | None = None
    reconnect_count: int = 0
    error: str | None = None


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_chat_id: str
    title: str | None
    chat_type: str
    participants_count: int
    messages_count: int
    selected: bool

    @classmethod
    def from_chat(cls, chat: Chat) -> ChatOut:
        return cls(
            id=chat.id,
            external_chat_id=chat.external_chat_id,
            title=chat.title,
            chat_type=chat.chat_type,
            participants_count=chat.participants_count,
            messages_count=chat.messages_count,
            selected=chat.selected,
        )


class ChatSelectionIn(BaseModel):
    chat_ids: list[str] = Field(default_factory=list)


class ChatSelectionOut(BaseModel):
    account_id: str
    selected_chat_ids: list[str]
    chats: list[ChatOut]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    platform: str
    external_message_id: str
    external_chat_id: str
    author_external_id: str | None
    author_name: str | None
    text: str
    timestamp: datetime
    attachments: list[dict[str, Any]]
    processing_status: str
    processing_error: str | None
    received_at: datetime

    @classmethod
    def from_message(cls, message: RawMessage) -> MessageOut:
        return cls(
            id=message.id,
            account_id=message.account_id,
            platform=message.platform,
            external_message_id=message.external_message_id,
            external_chat_id=message.external_chat_id,
            author_external_id=message.author_external_id,
            author_name=message.author_name,
            text=message.text,
            timestamp=message.timestamp,
            attachments=message.attachments or [],
            processing_status=message.processing_status,
            processing_error=message.processing_error,
            received_at=message.received_at,
        )


class ClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    message_id: str
    provider: str
    model: str | None
    prompt_version: str
    status: str
    is_order: bool | None
    confidence: float | None
    keywords: list[str]
    attributes: dict[str, Any]
    answers: dict[str, Any]
    usage: dict[str, Any]
    latency_ms: float | None
    error: str | None
    created_at: datetime

    @classmethod
    def from_classification(cls, record: Classification) -> ClassificationOut:
        return cls(
            id=record.id,
            message_id=record.message_id,
            provider=record.provider,
            model=record.model,
            prompt_version=record.prompt_version,
            status=record.status,
            is_order=record.is_order,
            confidence=record.confidence,
            keywords=record.keywords or [],
            attributes=record.attributes or {},
            answers=record.answers or {},
            usage=record.usage or {},
            latency_ms=record.latency_ms,
            error=record.error,
            created_at=record.created_at,
        )


class LabelIn(BaseModel):
    label: LabelValue
    labeler: str = "local"
    comment: str | None = None


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    message_id: str
    label: str
    labeler: str
    comment: str | None
    created_at: datetime

    @classmethod
    def from_label(cls, label: ManualLabel) -> LabelOut:
        return cls(
            id=label.id,
            message_id=label.message_id,
            label=label.label,
            labeler=label.labeler,
            comment=label.comment,
            created_at=label.created_at,
        )


class LabelImportItem(BaseModel):
    message_id: str
    label: LabelValue
    labeler: str = "local"
    comment: str | None = None


class LabelImportIn(BaseModel):
    labels: list[LabelImportItem]


class LabelImportOut(BaseModel):
    imported: int
    skipped: int


class ClassificationRunIn(BaseModel):
    account_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class ClassificationRunOut(BaseModel):
    processed: int
    failed: int
    run_id: str | None


class ExportRow(BaseModel):
    message: MessageOut
    classification: ClassificationOut


class MetricsOut(BaseModel):
    account_id: str | None
    messages: int
    classified_messages: int
    pending_messages: int
    manual_labels: int
    order_predictions: int
    average_jev_latency_ms: float | None
    quality: dict[str, float | int | None]
