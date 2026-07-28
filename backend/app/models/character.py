import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (Index("ix_characters_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    avatar_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    scenario: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str] = mapped_column(Text, default="")
    example_dialogue: Mapped[str] = mapped_column(Text, default="")
    generation_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    permissions: Mapped[dict] = mapped_column(JSONB, default=dict)
    image_profile_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tts_profile_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
