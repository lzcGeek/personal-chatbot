from uuid import UUID

from pydantic import BaseModel, Field


class MediaGenerationRequest(BaseModel):
    idempotency_key: UUID
    profile_id: str | None = Field(default=None, max_length=120)
    prompt: str | None = Field(default=None, max_length=10000)
