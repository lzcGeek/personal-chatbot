"""Add memory conflict provenance and effective time.

Revision ID: 20260728_0008
Revises: 20260728_0007
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260728_0008"
down_revision: Union[str, None] = "20260728_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memory_entries", sa.Column("conflict_reason", sa.Text(), nullable=True))
    op.add_column("memory_entries", sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memory_entries", sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("memory_entries", "effective_to")
    op.drop_column("memory_entries", "effective_from")
    op.drop_column("memory_entries", "conflict_reason")
