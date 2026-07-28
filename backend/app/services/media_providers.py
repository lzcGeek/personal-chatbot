import base64
from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI


@dataclass(frozen=True)
class GeneratedMedia:
    content: bytes
    mime_type: str


class ImageProvider(Protocol):
    async def generate(self, prompt: str, profile_id: str) -> GeneratedMedia: ...


class TtsProvider(Protocol):
    async def generate(self, text: str, profile_id: str) -> GeneratedMedia: ...


class OpenAICompatibleImageProvider:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, max_bytes: int) -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model
        self.max_bytes = max_bytes

    async def generate(self, prompt: str, profile_id: str) -> GeneratedMedia:
        response = await self.client.images.generate(
            model=self.model, prompt=prompt, response_format="b64_json"
        )
        encoded = response.data[0].b64_json if response.data else None
        if not encoded:
            raise ValueError("Image provider did not return inline image data")
        content = base64.b64decode(encoded, validate=True)
        return self._validated(content)

    def _validated(self, content: bytes) -> GeneratedMedia:
        if len(content) > self.max_bytes:
            raise ValueError("Generated image exceeds the configured limit")
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif content.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            raise ValueError("Image provider returned an unsupported media type")
        return GeneratedMedia(content, mime)


class OpenAICompatibleTtsProvider:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, max_bytes: int) -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model
        self.max_bytes = max_bytes

    async def generate(self, text: str, profile_id: str) -> GeneratedMedia:
        response = await self.client.audio.speech.create(
            model=self.model, voice=profile_id, input=text, response_format="mp3"
        )
        content = await response.aread()
        if len(content) > self.max_bytes:
            raise ValueError("Generated audio exceeds the configured limit")
        if not (content.startswith(b"ID3") or content[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}):
            raise ValueError("TTS provider returned an unsupported media type")
        return GeneratedMedia(content, "audio/mpeg")


class MediaCapabilityRegistry:
    def __init__(
        self,
        image_provider: ImageProvider | None,
        tts_provider: TtsProvider | None,
        image_profiles: list[str],
        tts_profiles: list[str],
        max_bytes: int,
        max_tasks_per_message: int,
    ) -> None:
        self.image_provider = image_provider
        self.tts_provider = tts_provider
        self.image_profiles = image_profiles if image_provider else []
        self.tts_profiles = tts_profiles if tts_provider else []
        self.max_bytes = max_bytes
        self.max_tasks_per_message = max_tasks_per_message

    def capabilities(self) -> dict[str, object]:
        return {
            "image": {"enabled": self.image_provider is not None, "profiles": self.image_profiles},
            "tts": {"enabled": self.tts_provider is not None, "profiles": self.tts_profiles},
            "limits": {
                "max_response_bytes": self.max_bytes,
                "max_tasks_per_message": self.max_tasks_per_message,
                "automatic_generation": False,
            },
        }

    def resolve(self, kind: str, profile_id: str | None):
        if kind == "image":
            provider, profiles = self.image_provider, self.image_profiles
        elif kind == "tts":
            provider, profiles = self.tts_provider, self.tts_profiles
        else:
            raise ValueError("Unsupported media kind")
        if provider is None:
            raise ValueError(f"{kind} provider is unavailable")
        selected = profile_id or (profiles[0] if profiles else None)
        if selected not in profiles:
            raise ValueError("Media profile is not allowed")
        return provider, selected
