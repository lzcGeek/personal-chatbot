import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class McpServer(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_mcp_servers_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), index=True)
    transport: Mapped[str] = mapped_column(String(20))
    command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    args: Mapped[list[str]] = mapped_column(JSONB, default=list)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    env: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="disconnected")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_network: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
