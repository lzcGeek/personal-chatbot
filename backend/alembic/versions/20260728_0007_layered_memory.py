"""Add layered NPC memory persistence.

Revision ID: 20260728_0007
Revises: 20260728_0006
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0007"
down_revision: Union[str, None] = "20260728_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memory_entries", sa.Column("scope", sa.String(30), nullable=False, server_default="conversation_shared"))
    op.add_column("memory_entries", sa.Column("character_id", sa.Uuid(), nullable=True))
    op.add_column("memory_entries", sa.Column("validity", sa.String(20), nullable=False, server_default="active"))
    op.add_column("memory_entries", sa.Column("superseded_by_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_memory_character", "memory_entries", "characters", ["character_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_memory_superseded_by", "memory_entries", "memory_entries", ["superseded_by_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_memory_entries_scope", "memory_entries", ["scope"])
    op.create_index("ix_memory_entries_character_id", "memory_entries", ["character_id"])
    op.create_index("ix_memory_entries_validity", "memory_entries", ["validity"])
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False), sa.Column("start_message_id", sa.BigInteger(), nullable=False),
        sa.Column("end_message_id", sa.BigInteger(), nullable=False), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_summaries_conversation_range", "conversation_summaries", ["conversation_id", "start_message_id", "end_message_id"])
    op.create_index("ix_conversation_summaries_user_id", "conversation_summaries", ["user_id"])
    op.create_index("ix_conversation_summaries_conversation_id", "conversation_summaries", ["conversation_id"])
    op.create_index("ix_conversation_summaries_status", "conversation_summaries", ["status"])
    op.create_table(
        "conversation_states", sa.Column("conversation_id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state_json", postgresql.JSONB(), nullable=False, server_default="{}"), sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_message_ids", postgresql.JSONB(), nullable=False, server_default="[]"), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index("ix_conversation_states_user_id", "conversation_states", ["user_id"])
    op.create_table(
        "compression_jobs", sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False), sa.Column("start_message_id", sa.BigInteger(), nullable=False), sa.Column("end_message_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compression_jobs_status_retry", "compression_jobs", ["status", "next_retry_at"])
    op.create_index("ix_compression_jobs_user_id", "compression_jobs", ["user_id"])
    op.create_index("ix_compression_jobs_conversation_id", "compression_jobs", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("compression_jobs")
    op.drop_table("conversation_states")
    op.drop_table("conversation_summaries")
    op.drop_index("ix_memory_entries_validity", table_name="memory_entries")
    op.drop_index("ix_memory_entries_character_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_scope", table_name="memory_entries")
    op.drop_constraint("fk_memory_superseded_by", "memory_entries", type_="foreignkey")
    op.drop_constraint("fk_memory_character", "memory_entries", type_="foreignkey")
    op.drop_column("memory_entries", "superseded_by_id")
    op.drop_column("memory_entries", "validity")
    op.drop_column("memory_entries", "character_id")
    op.drop_column("memory_entries", "scope")
