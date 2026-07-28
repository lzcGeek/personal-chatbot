import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.character import ConversationMemberWrite


RetrievalMode = Literal["auto", "off", "vector", "hybrid"]


class ConversationSettingsUpdate(BaseModel):
    retrieval_mode: RetrievalMode | None = None
    mode: Literal["assistant", "single_character", "group"] | None = None
    routing_strategy: Literal["manual", "mention", "round_robin", "auto"] | None = None
    scene_description: str | None = Field(default=None, max_length=20000)
    max_speakers_per_turn: int | None = Field(default=None, ge=1, le=8)
    max_group_generations: int | None = Field(default=None, ge=1, le=12)


class ConversationMembersUpdate(BaseModel):
    members: list[ConversationMemberWrite] = Field(max_length=50)

    @model_validator(mode="after")
    def reject_duplicates(self):
        ids: list[UUID] = [item.character_id for item in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("conversation members must be unique")
        return self


class ConversationStateUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    state: dict
    source_message_ids: list[Annotated[int, Field(gt=0)]] = Field(
        default_factory=list, max_length=100
    )

    @model_validator(mode="after")
    def validate_state_size(self):
        if len(json.dumps(self.state, ensure_ascii=False)) > 50_000:
            raise ValueError("scene state must not exceed 50000 characters")
        if len(self.source_message_ids) != len(set(self.source_message_ids)):
            raise ValueError("source message ids must be unique")
        return self
