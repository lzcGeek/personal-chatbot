import shutil
import uuid
from pathlib import Path

from app.services.media_providers import GeneratedMedia


EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "audio/mpeg": ".mp3",
}


class MediaStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        media: GeneratedMedia,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        attachment_id: uuid.UUID,
    ) -> Path:
        extension = EXTENSIONS.get(media.mime_type)
        if extension is None or not media.content:
            raise ValueError("Unsupported or empty generated media")
        directory = (self.root / str(user_id) / str(conversation_id)).resolve()
        if not directory.is_relative_to(self.root):
            raise ValueError("Invalid media storage path")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{attachment_id}{extension}"
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(media.content)
        temporary.replace(target)
        return target

    def validate_owned_path(self, path: str, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Path:
        candidate = Path(path).resolve()
        directory = (self.root / str(user_id) / str(conversation_id)).resolve()
        if not candidate.is_relative_to(directory) or not candidate.is_file():
            raise ValueError("Invalid media path")
        return candidate

    def delete_file(self, path: str) -> None:
        candidate = Path(path).resolve()
        if candidate.is_relative_to(self.root):
            candidate.unlink(missing_ok=True)

    def delete_conversation(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        directory = (self.root / str(user_id) / str(conversation_id)).resolve()
        if directory.is_relative_to(self.root):
            shutil.rmtree(directory, ignore_errors=True)
