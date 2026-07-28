import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.chat_message import ChatMessage
from app.models.speaker_plan import SpeakerPlan
from app.services.chat_service import ChatService
from app.services.llm_client import LlmTurn
from app.services.chat_errors import ChatFailure
from app.services.npc_orchestrator import NpcOrchestrator


def character(name: str):
    return SimpleNamespace(id=uuid.uuid4(), name=name)


class RouterLlm:
    def __init__(self, result):
        self.result = result

    async def route_characters(self, content, candidates, max_speakers):
        return self.result


@pytest.mark.asyncio
async def test_manual_routing_requires_an_enabled_target() -> None:
    alice, bob = character("Alice"), character("Bob")
    orchestrator = NpcOrchestrator(RouterLlm([]))  # type: ignore[arg-type]

    decision = await orchestrator.select(
        "manual", "hello", [alice, bob], target_character_id=bob.id
    )

    assert decision.speaker_ids == [bob.id]
    assert decision.reason_code == "manual_target"
    with pytest.raises(ValueError, match="enabled target"):
        await orchestrator.select(
            "manual", "hello", [alice, bob], target_character_id=uuid.uuid4()
        )


@pytest.mark.asyncio
async def test_mention_and_round_robin_are_deterministic() -> None:
    alice, bob = character("Alice"), character("Bob")
    orchestrator = NpcOrchestrator(RouterLlm([]))  # type: ignore[arg-type]

    mention = await orchestrator.select("mention", "@Bob take the gate", [alice, bob])
    rotation = await orchestrator.select(
        "round_robin", "continue", [alice, bob], previous_character_id=alice.id
    )

    assert mention.speaker_ids == [bob.id]
    assert mention.reason_code == "mention_unique"
    assert rotation.speaker_ids == [bob.id]

    ambiguous = await orchestrator.select("mention", "everyone continue", [alice, bob])
    wrapped = await orchestrator.select(
        "round_robin", "continue", [alice, bob], previous_character_id=bob.id
    )
    assert ambiguous.speaker_ids == [alice.id]
    assert ambiguous.reason_code == "mention_ambiguous_fallback"
    assert wrapped.speaker_ids == [alice.id]


@pytest.mark.asyncio
async def test_auto_router_rejects_unknown_output_and_enforces_limit() -> None:
    alice, bob = character("Alice"), character("Bob")
    invalid = NpcOrchestrator(RouterLlm([str(uuid.uuid4())]))  # type: ignore[arg-type]
    valid = NpcOrchestrator(RouterLlm([str(alice.id), str(bob.id)]))  # type: ignore[arg-type]

    fallback = await invalid.select("auto", "hello", [alice, bob], max_speakers=2)
    bounded = await valid.select("auto", "hello", [alice, bob], max_speakers=1)

    assert fallback.speaker_ids == [alice.id]
    assert fallback.reason_code == "auto_invalid_fallback"
    assert bounded.speaker_ids == [alice.id]

    duplicate = NpcOrchestrator(RouterLlm([str(alice.id), str(alice.id)]))  # type: ignore[arg-type]
    duplicate_fallback = await duplicate.select(
        "auto", "hello", [alice, bob], max_speakers=2
    )
    assert duplicate_fallback.reason_code == "auto_invalid_fallback"


def test_speaker_plan_is_request_unique_and_message_attribution_is_optional() -> None:
    constraints = {constraint.name for constraint in SpeakerPlan.__table__.constraints}
    assert "uq_speaker_plan_request" in constraints
    assert ChatMessage.__table__.c.speaker_plan_id.nullable is True


def response_message(message_id, speaker, plan_id, index):
    return SimpleNamespace(
        id=message_id,
        role="assistant",
        content=f"response-{index}",
        status="complete",
        citations=[],
        allow_network=False,
        client_request_id=None,
        character_id=speaker.id,
        speaker_name=speaker.name,
        speaker_plan_id=plan_id,
        speaker_plan_index=index,
        created_at=datetime.now(timezone.utc),
    )


def group_service():
    return ChatService(
        session_factory=None,  # type: ignore[arg-type]
        llm_client=None,  # type: ignore[arg-type]
        context_builder=None,  # type: ignore[arg-type]
        mcp_manager=None,  # type: ignore[arg-type]
        memory_service=None,  # type: ignore[arg-type]
        max_tool_rounds=1,
        npc_orchestrator=SimpleNamespace(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_group_execution_persists_each_speaker_before_building_the_next(monkeypatch) -> None:
    service = group_service()
    alice, bob = character("Alice"), character("Bob")
    plan = SimpleNamespace(
        id=uuid.uuid4(), status="pending", current_index=0,
        speaker_ids=[str(alice.id), str(bob.id)], strategy="auto", reason_code="auto_selected",
    )
    user = SimpleNamespace(id=1, content="hello")
    conversation = SimpleNamespace(id=uuid.uuid4())
    calls = []
    plan_updates = []

    async def prepare(*args):
        return user, conversation, plan, [alice, bob]

    async def build(*args):
        calls.append(("build", args[3].name))
        return [], [], [], [], False

    async def execute(*args):
        return LlmTurn(content="ok")

    async def save(content, conversation_id, citations, speaker, plan_id, index):
        calls.append(("save", speaker.name))
        return response_message(index + 2, speaker, plan_id, index)

    monkeypatch.setattr(service, "_prepare_group_request", prepare)
    monkeypatch.setattr(service, "_group_responses", lambda *args: async_value([]))
    monkeypatch.setattr(service, "_build_group_context", build)
    monkeypatch.setattr(service, "_execute_speaker", execute)
    monkeypatch.setattr(service, "_save_group_response", save)
    async def update_plan(*args, **kwargs):
        plan_updates.append(kwargs)

    monkeypatch.setattr(service, "_update_group_plan", update_plan)
    monkeypatch.setattr(service, "_schedule_memory", lambda *args: None)

    result = await service._send_group(  # noqa: SLF001
        "hello", uuid.uuid4(), conversation.id, False, uuid.uuid4(), uuid.uuid4(), None, 2
    )

    assert calls == [("build", "Alice"), ("save", "Alice"), ("build", "Bob"), ("save", "Bob")]
    assert result.speaker_name == "Bob"
    assert plan_updates[-1]["status"] == "complete"
    assert isinstance(plan_updates[-1]["duration_ms"], int)


@pytest.mark.asyncio
async def test_group_stream_reports_partial_failure_and_keeps_completed_messages(monkeypatch) -> None:
    service = group_service()
    alice, bob = character("Alice"), character("Bob")
    plan = SimpleNamespace(
        id=uuid.uuid4(), status="pending", current_index=0,
        speaker_ids=[str(alice.id), str(bob.id)], strategy="auto", reason_code="auto_selected",
    )
    user = SimpleNamespace(id=1, content="hello")
    conversation = SimpleNamespace(id=uuid.uuid4())
    attempts = 0
    plan_updates = []

    async def prepare(*args):
        return user, conversation, plan, [alice, bob]

    async def build(*args):
        return [], [], [], [], False

    async def execute(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("later speaker failed")
        return LlmTurn(content="ok")

    async def save(content, conversation_id, citations, speaker, plan_id, index):
        return response_message(index + 2, speaker, plan_id, index)

    monkeypatch.setattr(service, "_prepare_group_request", prepare)
    monkeypatch.setattr(service, "_group_responses", lambda *args: async_value([]))
    monkeypatch.setattr(service, "_build_group_context", build)
    monkeypatch.setattr(service, "_execute_speaker", execute)
    monkeypatch.setattr(service, "_save_group_response", save)
    async def update_plan(*args, **kwargs):
        plan_updates.append(kwargs)

    monkeypatch.setattr(service, "_update_group_plan", update_plan)
    monkeypatch.setattr(service, "_schedule_memory", lambda *args: None)

    events = [event async for event in service._stream_group(  # noqa: SLF001
        "hello", uuid.uuid4(), conversation.id, False, uuid.uuid4(), uuid.uuid4(), None, 2
    )]

    assert [event["type"] for event in events] == [
        "routing", "speaker_start", "token", "speaker_done", "speaker_start", "error"
    ]
    assert events[-1]["partial_saved"] is True
    assert events[-1]["completed_messages"][0]["speaker_name"] == "Alice"
    assert plan_updates[-1]["status"] == "failed"
    assert plan_updates[-1]["error_code"] == "generation_failed"


@pytest.mark.asyncio
async def test_completed_group_plan_replays_without_generation(monkeypatch) -> None:
    service = group_service()
    alice = character("Alice")
    plan = SimpleNamespace(
        id=uuid.uuid4(), status="complete", current_index=1,
        speaker_ids=[str(alice.id)], strategy="manual", reason_code="manual_target",
    )
    replay = response_message(2, alice, plan.id, 0)

    async def prepare(*args):
        return SimpleNamespace(id=1, content="hello"), SimpleNamespace(id=uuid.uuid4()), plan, [alice]

    monkeypatch.setattr(service, "_prepare_group_request", prepare)
    monkeypatch.setattr(service, "_group_responses", lambda *args: async_value([replay]))

    result = await service._send_group(  # noqa: SLF001
        "hello", uuid.uuid4(), uuid.uuid4(), False, uuid.uuid4(), uuid.uuid4(), alice.id, 1
    )

    assert result is replay


async def async_value(value):
    return value


def test_chat_rate_limit_is_bounded_per_user() -> None:
    service = group_service()
    service.requests_per_minute = 2
    user_id = uuid.uuid4()

    service._check_rate_limit(user_id)  # noqa: SLF001
    service._check_rate_limit(user_id)  # noqa: SLF001
    with pytest.raises(ChatFailure) as exc_info:
        service._check_rate_limit(user_id)  # noqa: SLF001
    assert exc_info.value.code == "chat_rate_limit"


@pytest.mark.asyncio
async def test_group_feature_gate_rejects_execution_before_routing(monkeypatch) -> None:
    service = group_service()
    service.group_npc_enabled = False

    class ModeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def scalar(self, statement): return "group"

    service.session_factory = lambda: ModeSession()  # type: ignore[assignment]
    with pytest.raises(ChatFailure) as exc_info:
        await service._conversation_mode(uuid.uuid4(), uuid.uuid4())  # noqa: SLF001
    assert exc_info.value.code == "group_npc_disabled"
