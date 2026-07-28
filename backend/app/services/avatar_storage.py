import shutil
import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile


AVATAR_MEDIA_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class AvatarStorage:
    def __init__(self, root: Path, max_upload_bytes: int) -> None:
        self.root = root.resolve()
        self.max_upload_bytes = max_upload_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadFile, user_id: uuid.UUID, character_id: uuid.UUID) -> Path:
        extension = AVATAR_MEDIA_TYPES.get(upload.content_type or "")
        if extension is None:
            raise ValueError("Avatar must be PNG, JPEG, WebP, or GIF")
        directory = self._directory(user_id, character_id)
        temporary = directory / f"avatar{extension}.upload"
        target = directory / f"avatar{extension}"
        directory.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            async with aiofiles.open(temporary, "wb") as output:
                while chunk := await upload.read(256 * 1024):
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise ValueError("Avatar exceeds the configured upload limit")
                    await output.write(chunk)
            if size == 0:
                raise ValueError("Avatar is empty")
            for existing in directory.glob("avatar.*"):
                if existing != temporary:
                    existing.unlink(missing_ok=True)
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return target

    def delete(self, user_id: uuid.UUID, character_id: uuid.UUID) -> None:
        directory = self._directory(user_id, character_id)
        if directory.is_relative_to(self.root):
            shutil.rmtree(directory, ignore_errors=True)

    def validate_owned_path(self, path: str, user_id: uuid.UUID, character_id: uuid.UUID) -> Path:
        candidate = Path(path).resolve()
        directory = self._directory(user_id, character_id)
        if not candidate.is_relative_to(directory) or not candidate.is_file():
            raise ValueError("Invalid avatar path")
        return candidate

    def _directory(self, user_id: uuid.UUID, character_id: uuid.UUID) -> Path:
        directory = (self.root / str(user_id) / str(character_id)).resolve()
        if not directory.is_relative_to(self.root):
            raise ValueError("Invalid avatar storage path")
        return directory
