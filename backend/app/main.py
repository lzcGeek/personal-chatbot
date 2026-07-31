from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.characters import router as characters_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.mcp import router as mcp_router
from app.api.memories import router as memories_router
from app.api.media import router as media_router
from app.api.skills import router as skills_router
from app.core.config import get_settings
from app.core.database import SessionLocal, close_database, init_database
from app.core.vector_db import close_vector_database, init_vector_database, qdrant_client
from app.services.auth_service import AuthService
from app.services.avatar_storage import AvatarStorage
from app.services.chat_service import ChatService
from app.services.context_builder import ContextBuilder
from app.services.compression_service import CompressionService
from app.services.embedding_service import EmbeddingService
from app.services.graph_extractor import GraphExtractor
from app.services.graph_store import GraphStore
from app.services.document_chunker import DocumentChunker
from app.services.document_index_worker import DocumentIndexWorker
from app.services.document_knowledge_service import DocumentKnowledgeService
from app.services.document_parser import DocumentParser
from app.services.document_storage import DocumentStorage
from app.services.document_vector_store import DocumentVectorStore
from app.services.llm_client import LlmClient
from app.services.mcp_manager import McpManager
from app.services.memory_service import MemoryService
from app.services.media_providers import (
    MediaCapabilityRegistry,
    OpenAICompatibleImageProvider,
    OpenAICompatibleTtsProvider,
)
from app.services.media_storage import MediaStorage
from app.services.media_worker import MediaWorker
from app.services.qdrant_memory_store import QdrantMemoryStore
from app.services.skill_loader import SkillLoader
from app.services.vector_index_worker import VectorIndexWorker


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()
    await init_vector_database()
    app.state.settings = settings
    app.state.skill_loader = SkillLoader(settings.skills_path)
    app.state.skill_loader.load()
    app.state.auth_service = AuthService(
        session_factory=SessionLocal,
        session_ttl_hours=settings.session_ttl_hours,
    )
    app.state.avatar_storage = AvatarStorage(
        settings.avatar_storage_path, settings.avatar_max_upload_bytes
    )
    app.state.embedding_service = EmbeddingService(
        base_url=settings.resolved_embedding_base_url,
        api_key=settings.resolved_embedding_api_key,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        request_timeout_seconds=settings.embedding_request_timeout_seconds,
        max_retries=settings.embedding_max_retries,
    )
    app.state.llm_client = LlmClient(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        request_timeout_seconds=settings.llm_request_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_base_seconds=settings.llm_retry_base_seconds,
    )
    app.state.compression_service = CompressionService(
        session_factory=SessionLocal,
        llm_client=app.state.llm_client,
        trigger_messages=settings.summary_trigger_messages,
        keep_recent=settings.summary_keep_recent,
        poll_seconds=settings.summary_worker_poll_seconds,
        max_attempts=settings.summary_worker_max_attempts,
    )
    if settings.memory_compression_enabled:
        app.state.compression_service.start()
    image_provider = None
    if settings.image_generation_enabled:
        image_provider = OpenAICompatibleImageProvider(
            settings.image_provider_base_url or settings.openai_base_url,
            settings.image_provider_api_key or settings.openai_api_key,
            settings.image_provider_model,
            settings.media_request_timeout_seconds,
            settings.media_max_response_bytes,
        )
    tts_provider = None
    if settings.tts_enabled:
        tts_provider = OpenAICompatibleTtsProvider(
            settings.tts_provider_base_url or settings.openai_base_url,
            settings.tts_provider_api_key or settings.openai_api_key,
            settings.tts_provider_model,
            settings.media_request_timeout_seconds,
            settings.media_max_response_bytes,
        )
    app.state.media_registry = MediaCapabilityRegistry(
        image_provider,
        tts_provider,
        settings.image_profile_list,
        settings.tts_profile_list,
        settings.media_max_response_bytes,
        settings.media_max_tasks_per_message,
    )
    app.state.media_storage = MediaStorage(settings.media_storage_path)
    app.state.media_worker = MediaWorker(
        SessionLocal,
        app.state.media_registry,
        app.state.media_storage,
        settings.media_worker_poll_seconds,
        settings.media_worker_max_attempts,
    )
    app.state.media_worker.start()
    app.state.graph_store = None
    app.state.graph_extractor = None
    if settings.neo4j_enabled:
        app.state.graph_store = GraphStore(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        await app.state.graph_store.initialize()
        app.state.graph_extractor = GraphExtractor(
            app.state.llm_client,
            max_facts_per_chunk=settings.graph_max_facts_per_chunk,
        )
    app.state.vector_store = QdrantMemoryStore(
        client=qdrant_client,
        collection_name=settings.qdrant_collection,
    )
    app.state.document_storage = DocumentStorage(
        root=settings.document_storage_path,
        max_upload_bytes=settings.document_max_upload_bytes,
    )
    app.state.document_parser = DocumentParser(mode=settings.pdf_parser_mode)
    app.state.document_chunker = DocumentChunker(
        chunk_characters=settings.document_chunk_characters,
        overlap_characters=settings.document_chunk_overlap_characters,
        context_window=settings.document_context_window,
    )
    app.state.document_vector_store = DocumentVectorStore(
        client=qdrant_client,
        collection_name=settings.qdrant_document_collection,
    )
    app.state.document_worker = DocumentIndexWorker(
        session_factory=SessionLocal,
        storage=app.state.document_storage,
        parser=app.state.document_parser,
        chunker=app.state.document_chunker,
        embedding_service=app.state.embedding_service,
        vector_store=app.state.document_vector_store,
        graph_store=app.state.graph_store,
        graph_extractor=app.state.graph_extractor,
        poll_seconds=settings.document_worker_poll_seconds,
        max_attempts=settings.document_worker_max_attempts,
        graph_concurrency=settings.graph_index_concurrency,
        core_concurrency=settings.document_worker_concurrency,
        embedding_batch_size=settings.document_embedding_batch_size,
        embedding_concurrency=settings.document_embedding_concurrency,
    )
    app.state.document_worker.start()
    app.state.memory_service = MemoryService(
        session_factory=SessionLocal,
        embedding_service=app.state.embedding_service,
        vector_store=app.state.vector_store,
        embedding_model=settings.embedding_model,
        relevance_threshold=settings.memory_relevance_threshold,
        result_limit=settings.memory_result_limit,
    )
    app.state.document_knowledge_service = DocumentKnowledgeService(
        embedding_service=app.state.embedding_service,
        vector_store=app.state.document_vector_store,
        graph_store=app.state.graph_store,
        result_limit=settings.document_result_limit,
        relevance_threshold=settings.document_relevance_threshold,
        vector_candidate_limit=settings.document_vector_candidate_limit,
    )
    app.state.vector_worker = VectorIndexWorker(
        session_factory=SessionLocal,
        embedding_service=app.state.embedding_service,
        vector_store=app.state.vector_store,
        poll_seconds=settings.vector_worker_poll_seconds,
        max_attempts=settings.vector_worker_max_attempts,
    )
    app.state.vector_worker.start()
    app.state.mcp_manager = McpManager(
        session_factory=SessionLocal,
        allowed_commands=settings.mcp_stdio_allowed_command_set,
        reconnect_seconds=settings.mcp_reconnect_seconds,
        tool_timeout_seconds=settings.mcp_tool_timeout_seconds,
        network_tools_enabled=settings.network_tools_enabled,
    )
    await app.state.mcp_manager.restore()
    app.state.context_builder = ContextBuilder(
        skill_loader=app.state.skill_loader,
        memory_service=app.state.memory_service,
        document_knowledge_service=app.state.document_knowledge_service,
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
        compression_service=(
            app.state.compression_service if settings.memory_compression_enabled else None
        ),
        requests_per_minute=settings.chat_requests_per_minute,
        server_max_speakers=settings.server_max_speakers_per_turn,
        server_max_group_generations=settings.server_max_group_generations,
        single_npc_enabled=settings.single_npc_enabled,
        group_npc_enabled=settings.group_npc_enabled,
    )
    yield
    await app.state.document_worker.close()
    await app.state.vector_worker.close()
    await app.state.compression_service.close()
    await app.state.media_worker.close()
    await app.state.mcp_manager.close()
    if app.state.graph_store is not None:
        await app.state.graph_store.close()
    await close_vector_database()
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
app.include_router(auth_router)
app.include_router(characters_router)
app.include_router(documents_router)
app.include_router(memories_router)
app.include_router(media_router)
app.include_router(mcp_router)
app.include_router(conversations_router)
app.include_router(chat_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runtime-capabilities")
async def runtime_capabilities() -> dict[str, bool]:
    return {
        "single_npc": settings.single_npc_enabled,
        "group_npc": settings.group_npc_enabled,
        "memory_compression": settings.memory_compression_enabled,
        "image": settings.image_generation_enabled,
        "tts": settings.tts_enabled,
    }
