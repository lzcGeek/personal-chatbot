from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Memory MCP Chatbot"
    app_host: str = "127.0.0.1"
    app_port: int = 8021
    debug: bool = False

    openai_base_url: str
    openai_api_key: str
    openai_model: str

    database_url: str = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'data' / 'chatbot.db').as_posix()}"
    chroma_path: Path = BACKEND_DIR / "data" / "chroma"
    skills_path: Path = PROJECT_DIR / "skills"

    recent_message_limit: int = Field(default=30, ge=1, le=500)
    history_page_size: int = Field(default=30, ge=1, le=100)
    max_context_characters: int = Field(default=60000, ge=1000)
    memory_result_limit: int = Field(default=5, ge=1, le=20)
    memory_relevance_threshold: float = Field(default=0.55, ge=0, le=1)
    mcp_reconnect_seconds: float = Field(default=10, ge=1)
    mcp_tool_timeout_seconds: float = Field(default=60, ge=1)
    max_tool_rounds: int = Field(default=8, ge=1, le=20)
    mcp_stdio_allowed_commands: str = "npx,uvx"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("openai_base_url", "openai_api_key", "openai_model")
    @classmethod
    def reject_empty_llm_settings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def mcp_stdio_allowed_command_set(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.mcp_stdio_allowed_commands.split(",")
            if value.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
