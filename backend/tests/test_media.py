import uuid

import pytest

from app.core.config import Settings
from app.models.media_task import MediaTask
from app.models.message_attachment import MessageAttachment
from app.services.media_providers import (
    GeneratedMedia,
    MediaCapabilityRegistry,
    OpenAICompatibleImageProvider,
)
from app.services.media_storage import MediaStorage


class NoopProvider:
    async def generate(self, text, profile):
        return GeneratedMedia(b"ID3data", "audio/mpeg")


def test_media_features_are_disabled_by_default_and_capabilities_hide_secrets() -> None:
    assert Settings.model_fields["image_generation_enabled"].default is False
    assert Settings.model_fields["tts_enabled"].default is False
    registry = MediaCapabilityRegistry(None, None, ["secret-image"], ["secret-voice"], 1024, 2)

    capabilities = registry.capabilities()

    assert capabilities["image"] == {"enabled": False, "profiles": []}
    assert capabilities["tts"] == {"enabled": False, "profiles": []}
    assert "key" not in str(capabilities).lower()
    assert capabilities["limits"]["automatic_generation"] is False


def test_registry_rejects_unavailable_or_unknown_profiles() -> None:
    registry = MediaCapabilityRegistry(None, NoopProvider(), [], ["voice-a"], 1024, 2)

    with pytest.raises(ValueError, match="unavailable"):
        registry.resolve("image", "default")
    with pytest.raises(ValueError, match="not allowed"):
        registry.resolve("tts", "voice-b")
    provider, profile = registry.resolve("tts", None)
    assert provider is not None and profile == "voice-a"


def test_image_adapter_rejects_oversized_and_invalid_media() -> None:
    provider = object.__new__(OpenAICompatibleImageProvider)
    provider.max_bytes = 12

    with pytest.raises(ValueError, match="configured limit"):
        provider._validated(b"\x89PNG\r\n\x1a\n" + b"x" * 20)  # noqa: SLF001
    provider.max_bytes = 1024
    with pytest.raises(ValueError, match="unsupported"):
        provider._validated(b"<html>bad</html>")  # noqa: SLF001
    result = provider._validated(b"\x89PNG\r\n\x1a\n1234")  # noqa: SLF001
    assert result.mime_type == "image/png"


def test_media_storage_is_owner_scoped_and_cleanup_safe(tmp_path) -> None:
    storage = MediaStorage(tmp_path / "media")
    user_id, conversation_id, attachment_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    path = storage.save(
        GeneratedMedia(b"ID3audio", "audio/mpeg"), user_id, conversation_id, attachment_id
    )

    assert storage.validate_owned_path(str(path), user_id, conversation_id) == path
    with pytest.raises(ValueError, match="Invalid media path"):
        storage.validate_owned_path(str(path), uuid.uuid4(), conversation_id)
    storage.delete_conversation(user_id, conversation_id)
    assert not path.exists()


def test_media_persistence_has_idempotency_and_cascade_cleanup() -> None:
    constraints = {constraint.name for constraint in MediaTask.__table__.constraints}
    assert "uq_media_task_idempotency" in constraints
    for model in (MediaTask, MessageAttachment):
        fk = next(
            item for item in model.__table__.c.conversation_id.foreign_keys
            if item.target_fullname == "conversations.id"
        )
        assert fk.ondelete == "CASCADE"
