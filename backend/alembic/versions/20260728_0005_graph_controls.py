"""Add optional document graph and conversation retrieval controls.

Revision ID: 20260728_0005
Revises: 20260724_0004
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260728_0005"
down_revision: Union[str, None] = "20260724_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "graph_mode",
            sa.String(length=20),
            nullable=False,
            server_default="inherit",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "retrieval_mode",
            sa.String(length=20),
            nullable=False,
            server_default="auto",
        ),
    )
    op.create_check_constraint(
        "ck_documents_graph_mode",
        "documents",
        "graph_mode IN ('inherit', 'enabled', 'disabled')",
    )
    op.create_check_constraint(
        "ck_conversations_retrieval_mode",
        "conversations",
        "retrieval_mode IN ('auto', 'off', 'vector', 'hybrid')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversations_retrieval_mode", "conversations", type_="check"
    )
    op.drop_constraint("ck_documents_graph_mode", "documents", type_="check")
    op.drop_column("conversations", "retrieval_mode")
    op.drop_column("documents", "graph_mode")
