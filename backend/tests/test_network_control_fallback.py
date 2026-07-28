import logging
import uuid
from types import SimpleNamespace

import pytest
import httpx
from openai import BadRequestError

from app.schemas.chat import ChatRequest
from app.schemas.mcp import McpServerCreate
from app.services.chat_errors import classify_chat_failure
from app.services.chat_service import ChatService
from app.services.context_builder import ContextBuilder
from app.services.llm_client import LlmClient, LlmTurn
from app.services.mcp_manager import McpManager, ServerWorker
from app.services.observability import log_chat_outcome


class RunningTask:
    def done(self) -> bool:
        return False


def make_manager() -> tuple[McpManager, uuid.UUID, uuid.UUID]:
    manager = McpManager(  # type: ignore[arg-type]
        session_factory=None,
        allowed_commands={"npx"},
        reconnect_seconds=1,
        tool_timeout_seconds=1,
    )
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    worker = ServerWorker(
        task=RunningTask(),  # type: ignore[arg-type]
        tools=[
            {
                "name": "search",
                "description": "Search online",
                "inputSchema": {"type": "object"},
            }
        ],
    )
    manager._workers[1] = worker
    manager._tool_routes[(user_id, "web__search")] = (1, "search", True)
    manager._tool_routes[(other_user_id, "other__search")] = (1, "search", True)
    return manager, user_id, other_user_id


def test_request_and_mcp_network_defaults() -> None:
    conversation_id = uuid.uuid4()
    request = ChatRequest(message="hello", conversation_id=conversation_id)
    assert request.allow_network is False
    assert request.client_request_id is None

    stdio = McpServerCreate(name="local", transport="stdio", command="npx")
    remote = McpServerCreate(name="web", transport="http", url="https://example.com")
    assert stdio.resolved_requires_network is False
    assert remote.resolved_requires_network is True


def test_network_tool_filtering_and_user_isolation() -> None:
    manager, user_id, other_user_id = make_manager()
    assert manager.openai_tools(user_id, allow_network=False) == []
    assert [item["function"]["name"] for item in manager.openai_tools(user_id, True)] == [
        "web__search"
    ]
    assert [item["function"]["name"] for item in manager.openai_tools(other_user_id, True)] == [
        "other__search"
    ]


@pytest.mark.asyncio
async def test_execution_layer_rejects_forged_network_call() -> None:
    manager, user_id, _ = make_manager()
    result = await manager.execute_tool(
        user_id, "web__search", {"q": "secret"}, allow_network=False
    )
    assert result == {
        "ok": False,
        "code": "network_access_denied",
        "error": "Network access is not allowed for this request",
    }
    assert manager._workers[1].queue.empty()


class FlakyCompletions:
    def __init__(self, failures: int, result: object) -> None:
        self.failures = failures
        self.calls = 0
        self.result = result

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("temporary")
        return self.result


@pytest.mark.asyncio
async def test_llm_transient_retry_recovers(monkeypatch) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = FlakyCompletions(1, response)
    client = LlmClient("https://example.com/v1", "test", "model", max_retries=2)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def no_delay(attempt: int) -> None:
        return None

    monkeypatch.setattr(client, "_retry_delay", no_delay)
    turn = await client.complete([{"role": "user", "content": "hi"}])
    assert turn.content == "ok"
    assert completions.calls == 2


@pytest.mark.asyncio
async def test_llm_non_transient_error_is_not_retried(monkeypatch) -> None:
    completions = FlakyCompletions(0, None)

    async def reject(**kwargs):
        completions.calls += 1
        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(400, request=request)
        raise BadRequestError("bad request with secret", response=response, body={})

    completions.create = reject
    client = LlmClient("https://example.com/v1", "test", "model", max_retries=2)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    with pytest.raises(BadRequestError):
        await client.complete([{"role": "user", "content": "hi"}])
    assert completions.calls == 1


@pytest.mark.asyncio
async def test_llm_transient_retry_exhaustion(monkeypatch) -> None:
    completions = FlakyCompletions(10, None)
    client = LlmClient("https://example.com/v1", "test", "model", max_retries=2)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def no_delay(attempt: int) -> None:
        return None

    monkeypatch.setattr(client, "_retry_delay", no_delay)
    with pytest.raises(TimeoutError):
        await client.complete([{"role": "user", "content": "hi"}])
    assert completions.calls == 3


class BreakingStreamLlm:
    async def stream(self, messages, tools):
        yield {"type": "token", "content": "partial"}
        raise RuntimeError("api-key=secret internal=https://private.example")

    async def extract_facts(self, *args):
        return []


@pytest.mark.asyncio
async def test_stream_interruption_saves_partial_and_returns_safe_error(monkeypatch) -> None:
    service = ChatService(
        session_factory=None,  # type: ignore[arg-type]
        llm_client=BreakingStreamLlm(),  # type: ignore[arg-type]
        context_builder=None,  # type: ignore[arg-type]
        mcp_manager=None,  # type: ignore[arg-type]
        memory_service=None,  # type: ignore[arg-type]
        max_tool_rounds=1,
    )
    user_message = SimpleNamespace(id=1, content="hello")
    saved: list[tuple[str, str]] = []

    async def fake_build(*args, **kwargs):
        return user_message, [], [], [], [], None

    async def fake_save(content, status, conversation_id, citations):
        saved.append((content, status))
        return SimpleNamespace(
            id=2,
            role="assistant",
            content=content,
            status=status,
            citations=[],
            allow_network=False,
            client_request_id=None,
            created_at=SimpleNamespace(isoformat=lambda: "now"),
        )

    monkeypatch.setattr(service, "_persist_and_build", fake_build)
    monkeypatch.setattr(service, "_save_assistant", fake_save)
    events = [
        event
        async for event in service.stream(
            "hello", uuid.uuid4(), uuid.uuid4(), client_request_id=uuid.uuid4()
        )
    ]
    assert saved == [("partial", "interrupted")]
    assert events[-1]["type"] == "error"
    assert events[-1]["partial_saved"] is True
    assert events[-1]["message"] == "生成失败，请稍后重试。"
    assert "secret" not in str(events[-1])
    assert "private.example" not in str(events[-1])


def test_structured_logging_does_not_accept_request_content(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.chat.telemetry"):
        log_chat_outcome(
            request_id="safe-id",
            outcome="error",
            duration_ms=10,
            error_code="llm_unavailable",
            degradations=["network_tool_failed"],
        )
    text = caplog.text
    assert "safe-id" in text
    assert "api-key" not in text
    assert "private.example" not in text
    assert "attempts=" in text


def test_failure_mapping_hides_upstream_detail() -> None:
    failure = classify_chat_failure(RuntimeError("token=secret https://private.example"))
    assert failure.code == "generation_failed"
    assert "secret" not in failure.user_message
    assert "private.example" not in failure.user_message


class ContextSession:
    async def get(self, model, key):
        return None

    async def execute(self, statement):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [])
        )


class FailingMemory:
    async def search(self, *args):
        raise RuntimeError("memory secret")


class FailingDocuments:
    async def search(self, *args):
        raise RuntimeError("document secret")


class NoNetworkTools:
    def openai_tools(self, user_id, allow_network=False):
        return []

    def has_network_tools(self, user_id):
        return False


class NoSkills:
    def prompt_section(self, name):
        return None


@pytest.mark.asyncio
async def test_optional_context_failures_and_missing_network_tool_degrade() -> None:
    builder = ContextBuilder(
        skill_loader=NoSkills(),  # type: ignore[arg-type]
        memory_service=FailingMemory(),  # type: ignore[arg-type]
        document_knowledge_service=FailingDocuments(),  # type: ignore[arg-type]
        mcp_manager=NoNetworkTools(),  # type: ignore[arg-type]
        recent_message_limit=10,
        max_context_characters=10000,
    )
    message = SimpleNamespace(
        id=1,
        role="user",
        content="latest news",
        conversation_id=uuid.uuid4(),
    )
    messages, tools, _, _, degradations = await builder.build(
        ContextSession(),  # type: ignore[arg-type]
        message,
        uuid.uuid4(),
        allow_network=True,
    )
    assert tools == []
    assert set(degradations) == {
        "memory_retrieval_failed",
        "document_retrieval_failed",
        "network_tool_unavailable",
    }
    assert "No network tool is currently available" in messages[0]["content"]


class ToolLoopLlm:
    async def complete(self, messages, tools=None, temperature=0.7):
        if tools is not None:
            return LlmTurn(
                tool_calls=[
                    {
                        "id": "call-1",
                        "function": {"name": "web__search", "arguments": "{}"},
                    }
                ]
            )
        return LlmTurn(content="local fallback")


class FailingNetworkManager:
    async def execute_tool(self, user_id, name, arguments, allow_network=False):
        return {"ok": False, "code": "mcp_timeout", "error": "timed out"}

    def is_network_tool(self, user_id, name):
        return True


@pytest.mark.asyncio
async def test_tool_round_limit_uses_tool_disabled_final_synthesis() -> None:
    service = ChatService(
        session_factory=None,  # type: ignore[arg-type]
        llm_client=ToolLoopLlm(),  # type: ignore[arg-type]
        context_builder=None,  # type: ignore[arg-type]
        mcp_manager=FailingNetworkManager(),  # type: ignore[arg-type]
        memory_service=None,  # type: ignore[arg-type]
        max_tool_rounds=1,
    )
    degradations: list[str] = []
    turn = await service._run_tool_loop(
        [], [{"type": "function"}], uuid.uuid4(), True, degradations
    )
    assert turn.content == "local fallback"
    assert degradations == ["network_tool_failed", "tool_round_limit_reached"]


def test_chat_message_has_idempotency_constraint() -> None:
    from app.models.chat_message import ChatMessage

    constraints = {constraint.name for constraint in ChatMessage.__table__.constraints}
    assert "uq_chat_messages_conversation_client_request" in constraints


class CompleteStreamLlm:
    async def stream(self, messages, tools):
        yield {"type": "token", "content": "fallback answer"}
        yield {"type": "turn", "turn": LlmTurn(content="fallback answer")}

    async def extract_facts(self, *args):
        return []


@pytest.mark.asyncio
async def test_sse_done_includes_degradation_metadata(monkeypatch) -> None:
    service = ChatService(
        session_factory=None,  # type: ignore[arg-type]
        llm_client=CompleteStreamLlm(),  # type: ignore[arg-type]
        context_builder=None,  # type: ignore[arg-type]
        mcp_manager=None,  # type: ignore[arg-type]
        memory_service=None,  # type: ignore[arg-type]
        max_tool_rounds=1,
    )
    user_message = SimpleNamespace(id=1, content="hello")

    async def fake_build(*args, **kwargs):
        return user_message, [], [], [], ["memory_retrieval_failed"], None

    async def fake_save(content, status, conversation_id, citations):
        return SimpleNamespace(
            id=2,
            role="assistant",
            content=content,
            status=status,
            citations=[],
            allow_network=False,
            client_request_id=None,
            created_at=SimpleNamespace(isoformat=lambda: "now"),
        )

    monkeypatch.setattr(service, "_persist_and_build", fake_build)
    monkeypatch.setattr(service, "_save_assistant", fake_save)
    monkeypatch.setattr(service, "_schedule_memory", lambda *args: None)
    events = [
        event
        async for event in service.stream(
            "hello", uuid.uuid4(), uuid.uuid4(), client_request_id=uuid.uuid4()
        )
    ]
    assert events[-1]["type"] == "done"
    assert events[-1]["degraded"] is True
    assert events[-1]["degradations"] == ["memory_retrieval_failed"]
