import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_conversation_id_id", "conversation_id", "id"),
        UniqueConstraint(
            "conversation_id",
            "client_request_id",
            name="uq_chat_messages_conversation_client_request",
        ),
        UniqueConstraint(
            "speaker_plan_id",
            "speaker_plan_index",
            name="uq_chat_messages_speaker_plan_index",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="complete")
    citations: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    allow_network: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    speaker_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    speaker_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("speaker_plans.id", ondelete="SET NULL", use_alter=True), nullable=True, index=True
    )
    speaker_plan_index: Mapped[int | None] = mapped_column(nullable=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
