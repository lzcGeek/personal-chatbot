"""Add network classification and idempotent chat request fields.

Revision ID: 20260724_0004
Revises: 20260723_0003
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260724_0004"
down_revision: Union[str, None] = "20260723_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "requires_network",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        "UPDATE mcp_servers SET requires_network = true "
        "WHERE transport IN ('http', 'sse')"
    )
    op.add_column(
        "chat_messages",
        sa.Column("client_request_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "allow_network",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_unique_constraint(
        "uq_chat_messages_conversation_client_request",
        "chat_messages",
        ["conversation_id", "client_request_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_chat_messages_conversation_client_request",
        "chat_messages",
        type_="unique",
    )
    op.drop_column("chat_messages", "allow_network")
    op.drop_column("chat_messages", "client_request_id")
    op.drop_column("mcp_servers", "requires_network")
