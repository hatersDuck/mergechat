"""Phase 0 schema.

Revision ID: 0001_phase0
Revises:
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("encrypted_session_data", sa.LargeBinary(), nullable=True),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconnect_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_sessions_platform", "account_sessions", ["platform"])
    op.create_index("ix_account_sessions_status", "account_sessions", ["status"])

    op.create_table(
        "chats",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("external_chat_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("chat_type", sa.String(length=32), nullable=False),
        sa.Column("participants_count", sa.Integer(), nullable=False),
        sa.Column("messages_count", sa.Integer(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "external_chat_id", name="uq_chat_account_external"
        ),
    )
    op.create_index("ix_chats_account_id", "chats", ["account_id"])
    op.create_index("ix_chats_external_chat_id", "chats", ["external_chat_id"])
    op.create_index("ix_chats_selected", "chats", ["selected"])

    op.create_table(
        "raw_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("chat_id", sa.String(length=36), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("external_message_id", sa.String(length=128), nullable=False),
        sa.Column("external_chat_id", sa.String(length=128), nullable=False),
        sa.Column("author_external_id", sa.String(length=128), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "external_chat_id",
            "external_message_id",
            name="uq_message_platform_chat_external",
        ),
    )
    op.create_index("ix_raw_messages_account_id", "raw_messages", ["account_id"])
    op.create_index("ix_raw_messages_chat_id", "raw_messages", ["chat_id"])
    op.create_index(
        "ix_raw_messages_external_chat_id", "raw_messages", ["external_chat_id"]
    )
    op.create_index("ix_raw_messages_timestamp", "raw_messages", ["timestamp"])
    op.create_index(
        "ix_raw_messages_processing_status", "raw_messages", ["processing_status"]
    )

    op.create_table(
        "classifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_order", sa.Boolean(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("route_from", sa.String(length=255), nullable=True),
        sa.Column("route_to", sa.String(length=255), nullable=True),
        sa.Column("travel_date", sa.String(length=64), nullable=True),
        sa.Column("cargo_type", sa.String(length=64), nullable=True),
        sa.Column("price", sa.String(length=128), nullable=True),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"], ["raw_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_classifications_message_id", "classifications", ["message_id"]
    )
    op.create_index("ix_classifications_status", "classifications", ["status"])
    op.create_index("ix_classifications_is_order", "classifications", ["is_order"])

    op.create_table(
        "manual_labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("labeler", sa.String(length=128), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"], ["raw_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "labeler", name="uq_label_message_labeler"),
    )
    op.create_index("ix_manual_labels_message_id", "manual_labels", ["message_id"])
    op.create_index("ix_manual_labels_label", "manual_labels", ["label"])

    op.create_table(
        "processing_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_runs_kind", "processing_runs", ["kind"])
    op.create_index("ix_processing_runs_status", "processing_runs", ["status"])


def downgrade() -> None:
    op.drop_table("processing_runs")
    op.drop_table("manual_labels")
    op.drop_table("classifications")
    op.drop_table("raw_messages")
    op.drop_table("chats")
    op.drop_table("account_sessions")
