import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VectorOutbox(Base):
    __tablename__ = "vector_outbox"
    __table_args__ = (Index("ix_vector_outbox_status_next_retry", "status", "next_retry_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    memory_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
