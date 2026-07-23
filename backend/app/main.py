from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.mcp import router as mcp_router
from app.api.memories import router as memories_router
from app.api.skills import router as skills_router
from app.core.config import get_settings
from app.core.database import SessionLocal, close_database, init_database
from app.services.chat_service import ChatService
from app.services.context_builder import ContextBuilder
from app.services.llm_client import LlmClient
from app.services.mcp_manager import McpManager
from app.services.memory_service import MemoryService
from app.services.skill_loader import SkillLoader


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()
    app.state.skill_loader = SkillLoader(settings.skills_path)
    app.state.skill_loader.load()
    app.state.memory_service = MemoryService(
        path=settings.chroma_path,
        session_factory=SessionLocal,
        relevance_threshold=settings.memory_relevance_threshold,
        result_limit=settings.memory_result_limit,
    )
    app.state.mcp_manager = McpManager(
        session_factory=SessionLocal,
        allowed_commands=settings.mcp_stdio_allowed_command_set,
        reconnect_seconds=settings.mcp_reconnect_seconds,
        tool_timeout_seconds=settings.mcp_tool_timeout_seconds,
    )
    await app.state.mcp_manager.restore()
    app.state.llm_client = LlmClient(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )
    app.state.context_builder = ContextBuilder(
        skill_loader=app.state.skill_loader,
        memory_service=app.state.memory_service,
        mcp_manager=app.state.mcp_manager,
        recent_message_limit=settings.recent_message_limit,
        max_context_characters=settings.max_context_characters,
    )
    app.state.chat_service = ChatService(
        session_factory=SessionLocal,
        llm_client=app.state.llm_client,
        context_builder=app.state.context_builder,
        mcp_manager=app.state.mcp_manager,
        memory_service=app.state.memory_service,
        max_tool_rounds=settings.max_tool_rounds,
    )
    yield
    await app.state.mcp_manager.close()
    await close_database()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(skills_router)
app.include_router(memories_router)
app.include_router(mcp_router)
app.include_router(conversations_router)
app.include_router(chat_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
