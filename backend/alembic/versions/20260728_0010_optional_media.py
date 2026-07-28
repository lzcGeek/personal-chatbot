"""Add optional media tasks and private attachments.

Revision ID: 20260728_0010
Revises: 20260728_0009
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260728_0010"
down_revision: Union[str, None] = "20260728_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("provider_id", sa.String(80), nullable=False, server_default="openai-compatible"),
        sa.Column("profile_id", sa.String(120), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", "kind", name="uq_media_task_idempotency"),
    )
    op.create_index("ix_media_tasks_user_id", "media_tasks", ["user_id"])
    op.create_index("ix_media_tasks_conversation_id", "media_tasks", ["conversation_id"])
    op.create_index("ix_media_tasks_message_id", "media_tasks", ["message_id"])
    op.create_index("ix_media_tasks_status", "media_tasks", ["status"])
    op.create_index("ix_media_tasks_status_retry", "media_tasks", ["status", "next_retry_at"])
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("profile_id", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["media_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_message_attachments_user_id", "message_attachments", ["user_id"])
    op.create_index("ix_message_attachments_conversation_id", "message_attachments", ["conversation_id"])
    op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])


def downgrade() -> None:
    op.drop_table("message_attachments")
    op.drop_table("media_tasks")
