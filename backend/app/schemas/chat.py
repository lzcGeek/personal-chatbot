from pydantic import BaseModel, Field
from uuid import UUID


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: UUID
    allow_network: bool = False
    client_request_id: UUID | None = None
    target_character_id: UUID | None = None
    max_speakers: int | None = Field(default=None, ge=1, le=8)
    # Evaluation/debug trace. The full retrieval context is returned only for
    # this response and is never persisted in chat history.
    include_retrieval_context: bool = False
