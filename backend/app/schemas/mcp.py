from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class McpServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    transport: Literal["stdio", "sse", "http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: HttpUrl | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    requires_network: bool | None = None

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "McpServerCreate":
        if self.transport == "stdio" and not self.command:
            raise ValueError("command is required for stdio transport")
        if self.transport in {"sse", "http"} and self.url is None:
            raise ValueError("url is required for network transports")
        return self

    @property
    def resolved_requires_network(self) -> bool:
        if self.requires_network is not None:
            return self.requires_network
        return self.transport in {"sse", "http"}


class McpServerUpdate(BaseModel):
    requires_network: bool
