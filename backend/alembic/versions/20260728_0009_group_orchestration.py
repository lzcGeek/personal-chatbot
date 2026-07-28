"""Add persisted bounded group speaker plans.

Revision ID: 20260728_0009
Revises: 20260728_0008
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0009"
down_revision: Union[str, None] = "20260728_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("max_speakers_per_turn", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("conversations", sa.Column("max_group_generations", sa.Integer(), nullable=False, server_default="3"))
    op.create_table(
        "speaker_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_message_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("strategy", sa.String(30), nullable=False),
        sa.Column("speaker_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("current_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "request_id", name="uq_speaker_plan_request"),
    )
    op.create_index("ix_speaker_plans_user_id", "speaker_plans", ["user_id"])
    op.create_index("ix_speaker_plans_conversation_id", "speaker_plans", ["conversation_id"])
    op.create_index("ix_speaker_plans_status", "speaker_plans", ["status"])
    op.create_index("ix_speaker_plans_conversation_status", "speaker_plans", ["conversation_id", "status"])
    op.add_column("chat_messages", sa.Column("speaker_plan_id", sa.Uuid(), nullable=True))
    op.add_column("chat_messages", sa.Column("speaker_plan_index", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_chat_messages_speaker_plan", "chat_messages", "speaker_plans", ["speaker_plan_id"], ["id"], ondelete="SET NULL", use_alter=True)
    op.create_index("ix_chat_messages_speaker_plan_id", "chat_messages", ["speaker_plan_id"])
    op.create_unique_constraint("uq_chat_messages_speaker_plan_index", "chat_messages", ["speaker_plan_id", "speaker_plan_index"])


def downgrade() -> None:
    op.drop_constraint("uq_chat_messages_speaker_plan_index", "chat_messages", type_="unique")
    op.drop_index("ix_chat_messages_speaker_plan_id", table_name="chat_messages")
    op.drop_constraint("fk_chat_messages_speaker_plan", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "speaker_plan_id")
    op.drop_column("chat_messages", "speaker_plan_index")
    op.drop_table("speaker_plans")
    op.drop_column("conversations", "max_group_generations")
    op.drop_column("conversations", "max_speakers_per_turn")
