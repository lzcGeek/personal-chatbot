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

    database_url: str = "postgresql+asyncpg://newagent:newagent@127.0.0.1:5434/newagent"
    qdrant_url: str = "http://127.0.0.1:6335"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "conversation_memories_v1"
    qdrant_document_collection: str = "document_chunks_v1"

    neo4j_enabled: bool = True
    neo4j_uri: str = "bolt://127.0.0.1:7688"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "newagent-graph"
    graph_max_facts_per_chunk: int = Field(default=20, ge=1, le=100)
    graph_index_concurrency: int = Field(default=4, ge=1, le=16)

    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = Field(default=1536, ge=1)

    session_cookie_name: str = "newagent_session"
    csrf_cookie_name: str = "newagent_csrf"
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 365)
    cookie_secure: bool = False
    allow_registration: bool = True
    skills_path: Path = PROJECT_DIR / "skills"
    document_storage_path: Path = BACKEND_DIR / "data" / "documents"
    avatar_storage_path: Path = BACKEND_DIR / "data" / "avatars"
    media_storage_path: Path = BACKEND_DIR / "data" / "media"
    avatar_max_upload_mb: int = Field(default=5, ge=1, le=20)
    media_max_response_mb: int = Field(default=15, ge=1, le=100)
    media_request_timeout_seconds: float = Field(default=60, ge=1, le=600)
    media_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    media_worker_max_attempts: int = Field(default=3, ge=1, le=20)
    media_max_tasks_per_message: int = Field(default=2, ge=1, le=10)
    image_generation_enabled: bool = False
    image_provider_base_url: str | None = None
    image_provider_api_key: str | None = None
    image_provider_model: str = "gpt-image-1"
    image_profiles: str = "default"
    tts_enabled: bool = False
    tts_provider_base_url: str | None = None
    tts_provider_api_key: str | None = None
    tts_provider_model: str = "tts-1"
    tts_profiles: str = "alloy"
    document_max_upload_mb: int = Field(default=25, ge=1, le=1024)
    document_chunk_characters: int = Field(default=1200, ge=200, le=10000)
    document_chunk_overlap_characters: int = Field(default=200, ge=0, le=2000)
    document_context_window: int = Field(default=1, ge=0, le=5)
    document_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    document_worker_max_attempts: int = Field(default=5, ge=1, le=100)
    document_result_limit: int = Field(default=6, ge=1, le=20)
    document_relevance_threshold: float = Field(default=0.45, ge=0, le=1)

    recent_message_limit: int = Field(default=30, ge=1, le=500)
    history_page_size: int = Field(default=30, ge=1, le=100)
    max_context_characters: int = Field(default=60000, ge=1000)
    memory_result_limit: int = Field(default=5, ge=1, le=20)
    memory_relevance_threshold: float = Field(default=0.55, ge=0, le=1)
    summary_trigger_messages: int = Field(default=40, ge=10, le=1000)
    summary_keep_recent: int = Field(default=20, ge=4, le=500)
    summary_worker_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    summary_worker_max_attempts: int = Field(default=5, ge=1, le=100)
    mcp_reconnect_seconds: float = Field(default=10, ge=1)
    mcp_tool_timeout_seconds: float = Field(default=60, ge=1)
    network_tools_enabled: bool = True
    max_tool_rounds: int = Field(default=8, ge=1, le=20)
    chat_requests_per_minute: int = Field(default=30, ge=1, le=1000)
    server_max_speakers_per_turn: int = Field(default=4, ge=1, le=8)
    server_max_group_generations: int = Field(default=6, ge=1, le=12)
    single_npc_enabled: bool = False
    group_npc_enabled: bool = False
    memory_compression_enabled: bool = False
    llm_request_timeout_seconds: float = Field(default=60, ge=1, le=600)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_retry_base_seconds: float = Field(default=0.5, ge=0.05, le=10)
    vector_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    vector_worker_max_attempts: int = Field(default=8, ge=1, le=100)
    mcp_stdio_allowed_commands: str = "npx,uvx"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("openai_base_url", "openai_api_key", "openai_model")
    @classmethod
    def reject_empty_llm_settings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("document_storage_path", "avatar_storage_path", "media_storage_path")
    @classmethod
    def resolve_document_storage_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (PROJECT_DIR / value).resolve()

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

    @property
    def resolved_embedding_base_url(self) -> str:
        return (self.embedding_base_url or self.openai_base_url).strip()

    @property
    def resolved_embedding_api_key(self) -> str:
        return (self.embedding_api_key or self.openai_api_key).strip()

    @property
    def document_max_upload_bytes(self) -> int:
        return self.document_max_upload_mb * 1024 * 1024

    @property
    def avatar_max_upload_bytes(self) -> int:
        return self.avatar_max_upload_mb * 1024 * 1024

    @property
    def media_max_response_bytes(self) -> int:
        return self.media_max_response_mb * 1024 * 1024

    @property
    def image_profile_list(self) -> list[str]:
        return [item.strip() for item in self.image_profiles.split(",") if item.strip()]

    @property
    def tts_profile_list(self) -> list[str]:
        return [item.strip() for item in self.tts_profiles.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
