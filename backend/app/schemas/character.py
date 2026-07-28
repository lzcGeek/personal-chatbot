from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


ALLOWED_PERMISSION_KEYS = {"network", "tools", "knowledge", "image", "tts"}


class CharacterWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=20000)
    personality: str = Field(default="", max_length=20000)
    scenario: str = Field(default="", max_length=20000)
    greeting: str = Field(default="", max_length=20000)
    example_dialogue: str = Field(default="", max_length=40000)
    generation_settings: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, bool] = Field(default_factory=dict)
    image_profile_id: str | None = Field(default=None, max_length=120)
    tts_profile_id: str | None = Field(default=None, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    @field_validator("generation_settings")
    @classmethod
    def validate_generation_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {"temperature", "top_p", "max_tokens"}
        if set(value) - allowed:
            raise ValueError("unsupported generation setting")
        if "temperature" in value and not 0 <= float(value["temperature"]) <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if "top_p" in value and not 0 <= float(value["top_p"]) <= 1:
            raise ValueError("top_p must be between 0 and 1")
        if "max_tokens" in value and not 1 <= int(value["max_tokens"]) <= 32768:
            raise ValueError("max_tokens must be between 1 and 32768")
        return value

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: dict[str, bool]) -> dict[str, bool]:
        if set(value) - ALLOWED_PERMISSION_KEYS:
            raise ValueError("unsupported character permission")
        return value


class CharacterCreate(CharacterWrite):
    pass


class CharacterUpdate(CharacterWrite):
    archived: bool = False


class CharacterInfo(CharacterWrite):
    id: UUID
    archived: bool
    has_avatar: bool
    created_at: datetime
    updated_at: datetime


class ConversationMemberWrite(BaseModel):
    character_id: UUID
    position: int = Field(default=0, ge=0, le=1000)
    enabled: bool = True
    overrides: dict[str, Any] = Field(default_factory=dict)


class ConversationMemberInfo(ConversationMemberWrite):
    id: UUID
    name: str
