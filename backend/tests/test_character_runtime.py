import io
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.api import characters as characters_api
from app.models.character import Character
from app.models.conversation import Conversation
from app.schemas.character import CharacterCreate
from app.schemas.conversation import ConversationMembersUpdate
from app.services.avatar_storage import AvatarStorage
from app.services.chat_service import ChatService
from app.services.compression_service import CompressionService
from app.services.llm_client import LlmTurn
from app.services.memory_service import MemoryService


def test_character_accepts_minimal_definition_with_safe_defaults() -> None:
    character = CharacterCreate(name="  守卫  ")

    assert character.name == "守卫"
    assert character.permissions == {}
    assert character.generation_settings == {}
    assert character.description == ""


@pytest.mark.parametrize(
    "settings",
    [
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"top_p": 1.1},
        {"max_tokens": 0},
        {"unknown": True},
    ],
)
def test_character_rejects_unsafe_generation_settings(settings) -> None:
    with pytest.raises(ValidationError):
        CharacterCreate(name="NPC", generation_settings=settings)


def test_character_permissions_are_an_allowlist() -> None:
    assert CharacterCreate(name="NPC", permissions={"knowledge": True}).permissions == {
        "knowledge": True
    }
    with pytest.raises(ValidationError):
        CharacterCreate(name="NPC", permissions={"admin": True})


def test_conversation_member_payload_rejects_duplicate_characters() -> None:
    character_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        ConversationMembersUpdate(
            members=[
                {"character_id": character_id, "position": 0},
                {"character_id": character_id, "position": 1},
            ]
        )


def test_legacy_conversation_and_character_defaults_are_backward_compatible() -> None:
    assert Conversation.__table__.c.mode.default.arg == "assistant"
    assert Conversation.__table__.c.routing_strategy.default.arg == "manual"
    assert Character.__table__.c.archived.default.arg is False


def test_character_message_has_snapshot_while_legacy_shape_stays_unchanged() -> None:
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        role="assistant",
        content="hello",
        status="complete",
        citations=[],
        allow_network=False,
        client_request_id=None,
        created_at=now,
    )
    legacy = ChatService.serialize_message(SimpleNamespace(**base))  # type: ignore[arg-type]
    character_id = uuid.uuid4()
    npc = ChatService.serialize_message(  # type: ignore[arg-type]
        SimpleNamespace(**base, character_id=character_id, speaker_name="守卫")
    )

    assert "character_id" not in legacy and "speaker_name" not in legacy
    assert npc["character_id"] == str(character_id)
    assert npc["speaker_name"] == "守卫"


def avatar_upload(content: bytes, media_type: str) -> UploadFile:
    return UploadFile(
        filename="avatar.png",
        file=io.BytesIO(content),
        headers=Headers({"content-type": media_type}),
    )


@pytest.mark.asyncio
async def test_avatar_storage_is_private_and_replacement_safe(tmp_path) -> None:
    storage = AvatarStorage(tmp_path / "avatars", max_upload_bytes=20)
    user_id, character_id = uuid.uuid4(), uuid.uuid4()

    first = await storage.save(avatar_upload(b"first", "image/png"), user_id, character_id)
    second = await storage.save(avatar_upload(b"second", "image/webp"), user_id, character_id)

    assert not first.exists()
    assert second.read_bytes() == b"second"
    assert storage.validate_owned_path(str(second), user_id, character_id) == second
    with pytest.raises(ValueError, match="Invalid avatar path"):
        storage.validate_owned_path(str(second), user_id, uuid.uuid4())


@pytest.mark.asyncio
async def test_avatar_storage_rejects_type_and_size(tmp_path) -> None:
    storage = AvatarStorage(tmp_path / "avatars", max_upload_bytes=3)

    with pytest.raises(ValueError, match="PNG"):
        await storage.save(
            avatar_upload(b"text", "text/plain"), uuid.uuid4(), uuid.uuid4()
        )
    with pytest.raises(ValueError, match="upload limit"):
        await storage.save(
            avatar_upload(b"large", "image/png"), uuid.uuid4(), uuid.uuid4()
        )


class CaptureSession:
    def __init__(self) -> None:
        self.statement = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def scalar(self, statement):
        self.statement = statement
        return None


@pytest.mark.asyncio
async def test_character_lookup_is_scoped_by_owner_and_soft_delete(monkeypatch) -> None:
    session = CaptureSession()
    monkeypatch.setattr(characters_api, "SessionLocal", lambda: session)

    assert await characters_api.owned_character(uuid.uuid4(), uuid.uuid4()) is None

    sql = str(session.statement)
    assert "characters.user_id" in sql
    assert "characters.deleted_at IS NULL" in sql


class CharacterStreamLlm:
    async def stream(self, messages, tools):
        yield {"type": "token", "content": "halt"}
        yield {"type": "turn", "turn": LlmTurn(content="halt")}


@pytest.mark.asyncio
async def test_single_character_stream_attributes_tokens_and_persisted_message(monkeypatch) -> None:
    service = ChatService(
        session_factory=None,  # type: ignore[arg-type]
        llm_client=CharacterStreamLlm(),  # type: ignore[arg-type]
        context_builder=None,  # type: ignore[arg-type]
        mcp_manager=None,  # type: ignore[arg-type]
        memory_service=None,  # type: ignore[arg-type]
        max_tool_rounds=1,
    )
    user_message = SimpleNamespace(id=1, content="hello")
    speaker = SimpleNamespace(id=uuid.uuid4(), name="Guard")

    async def fake_build(*args, **kwargs):
        return user_message, [], [], [], [], None, speaker, False

    async def fake_save(content, status, conversation_id, citations, saved_speaker):
        assert saved_speaker is speaker
        return SimpleNamespace(
            id=2, role="assistant", content=content, status=status, citations=[],
            allow_network=False, client_request_id=None,
            character_id=speaker.id, speaker_name=speaker.name,
            created_at=SimpleNamespace(isoformat=lambda: "now"),
        )

    monkeypatch.setattr(service, "_persist_and_build", fake_build)
    monkeypatch.setattr(service, "_save_assistant", fake_save)
    monkeypatch.setattr(service, "_schedule_memory", lambda *args: None)

    events = [event async for event in service.stream("hello", uuid.uuid4(), uuid.uuid4())]

    assert [event["type"] for event in events] == [
        "speaker_start", "token", "speaker_done", "done"
    ]
    assert events[1]["character_id"] == str(speaker.id)
    assert events[-1]["message"]["speaker_name"] == "Guard"


class DenyToolManager:
    def __init__(self) -> None:
        self.called = False

    async def execute_tool(self, *args, **kwargs):
        self.called = True
        return {"ok": True}


@pytest.mark.asyncio
async def test_execution_rejects_tool_not_present_in_effective_allowlist() -> None:
    manager = DenyToolManager()
    service = ChatService(
        session_factory=None,  # type: ignore[arg-type]
        llm_client=None,  # type: ignore[arg-type]
        context_builder=None,  # type: ignore[arg-type]
        mcp_manager=manager,  # type: ignore[arg-type]
        memory_service=None,  # type: ignore[arg-type]
        max_tool_rounds=1,
    )
    degradations: list[str] = []
    result = await service._execute_tool_call(  # noqa: SLF001
        {"id": "1", "function": {"name": "admin_tool", "arguments": "{}"}},
        uuid.uuid4(), False, degradations, set(),
    )

    assert manager.called is False
    assert "mcp_tool_not_authorized" in result["content"]
    assert degradations == ["mcp_tool_not_authorized"]


@pytest.mark.parametrize(
    ("decision", "found", "expected"),
    [
        ("coexist", False, ("active", None)),
        ("replace_explicit", True, ("active", "superseded")),
        ("state_change", True, ("active", "historical")),
        ("replace_explicit", False, ("pending_confirmation", None)),
        ("pending_confirmation", True, ("pending_confirmation", None)),
    ],
)
def test_hybrid_memory_conflict_policy(decision, found, expected) -> None:
    assert MemoryService._candidate_outcome(decision, found) == expected  # noqa: SLF001


def test_summary_range_preserves_recent_messages_and_waits_for_threshold() -> None:
    assert CompressionService._select_range(list(range(1, 40)), 40, 20) is None  # noqa: SLF001
    assert CompressionService._select_range(list(range(1, 41)), 40, 20) == (1, 20)  # noqa: SLF001
    assert CompressionService._select_range(list(range(21, 61)), 40, 10) == (21, 50)  # noqa: SLF001
