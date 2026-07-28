from uuid import UUID

from pydantic import BaseModel, Field


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=8, max_length=1024)


class UserInfo(BaseModel):
    id: UUID
    username: str
    display_name: str


class AuthResponse(BaseModel):
    user: UserInfo
