import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SpeakerPlan(Base):
    __tablename__ = "speaker_plans"
    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id", name="uq_speaker_plan_request"),
        Index("ix_speaker_plans_conversation_status", "conversation_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    strategy: Mapped[str] = mapped_column(String(30), nullable=False)
    speaker_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
