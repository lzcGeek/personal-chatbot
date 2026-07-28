import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MediaTask(Base):
    __tablename__ = "media_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", "kind", name="uq_media_task_idempotency"),
        Index("ix_media_tasks_status_retry", "status", "next_retry_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(80), default="openai-compatible")
    profile_id: Mapped[str] = mapped_column(String(120), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
