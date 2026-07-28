"""Add character runtime persistence.

Revision ID: 20260728_0006
Revises: 20260728_0005
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260728_0006"
down_revision: Union[str, None] = "20260728_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("avatar_path", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("personality", sa.Text(), nullable=False, server_default=""),
        sa.Column("scenario", sa.Text(), nullable=False, server_default=""),
        sa.Column("greeting", sa.Text(), nullable=False, server_default=""),
        sa.Column("example_dialogue", sa.Text(), nullable=False, server_default=""),
        sa.Column("generation_settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("image_profile_id", sa.String(length=120), nullable=True),
        sa.Column("tts_profile_id", sa.String(length=120), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_characters_user_id", "characters", ["user_id"])
    op.create_index("ix_characters_user_updated", "characters", ["user_id", "updated_at"])
    op.create_table(
        "conversation_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("overrides", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "character_id", name="uq_conversation_member"),
    )
    op.create_index("ix_conversation_members_user_id", "conversation_members", ["user_id"])
    op.create_index("ix_conversation_members_order", "conversation_members", ["conversation_id", "position"])
    op.add_column("conversations", sa.Column("mode", sa.String(length=30), nullable=False, server_default="assistant"))
    op.add_column("conversations", sa.Column("routing_strategy", sa.String(length=30), nullable=False, server_default="manual"))
    op.add_column("conversations", sa.Column("scene_description", sa.Text(), nullable=False, server_default=""))
    op.add_column("chat_messages", sa.Column("character_id", sa.Uuid(), nullable=True))
    op.add_column("chat_messages", sa.Column("speaker_name", sa.String(length=120), nullable=True))
    op.create_foreign_key("fk_chat_messages_character", "chat_messages", "characters", ["character_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_chat_messages_character_id", "chat_messages", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_character_id", table_name="chat_messages")
    op.drop_constraint("fk_chat_messages_character", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "speaker_name")
    op.drop_column("chat_messages", "character_id")
    op.drop_column("conversations", "scene_description")
    op.drop_column("conversations", "routing_strategy")
    op.drop_column("conversations", "mode")
    op.drop_table("conversation_members")
    op.drop_table("characters")
