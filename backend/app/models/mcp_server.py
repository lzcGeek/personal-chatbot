import logging
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, engine

logger = logging.getLogger(__name__)


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    transport: Mapped[str] = mapped_column(String(20))
    command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    args: Mapped[list[str]] = mapped_column(JSON, default=list)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    env: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="disconnected")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


async def migrate_enabled_column() -> None:
    """Add enabled column if it does not exist (pre-migration compatibility)."""
    try:
        async with engine.begin() as connection:
            await connection.execute(text("ALTER TABLE mcp_servers ADD COLUMN enabled BOOLEAN DEFAULT 1"))
    except Exception:
        logger.debug("enabled column already exists, skipping migration")
