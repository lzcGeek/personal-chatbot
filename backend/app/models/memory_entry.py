import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    __table_args__ = (
        Index("ix_memory_entries_user_conversation_created", "user_id", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text)
    source_message_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    scope: Mapped[str] = mapped_column(String(30), default="conversation_shared", index=True)
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("characters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    validity: Mapped[str] = mapped_column(String(20), default="active", index=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("memory_entries.id", ondelete="SET NULL"), nullable=True
    )
    conflict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    embedding_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_revision: Mapped[int] = mapped_column(Integer, default=1)
    last_embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
