import hashlib
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiofiles
from fastapi import UploadFile


@dataclass(frozen=True)
class StoredDocument:
    path: Path
    sha256: str
    byte_size: int


class DocumentStorage:
    def __init__(self, root: Path, max_upload_bytes: int) -> None:
        self.root = root.resolve()
        self.max_upload_bytes = max_upload_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        upload: UploadFile,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        extension: str,
    ) -> StoredDocument:
        directory = self._document_directory(user_id, document_id)
        directory.mkdir(parents=True, exist_ok=False)
        target = directory / f"source{extension}"
        digest = hashlib.sha256()
        size = 0
        try:
            async with aiofiles.open(target, "wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise ValueError("File exceeds the configured upload limit")
                    digest.update(chunk)
                    await output.write(chunk)
            if size == 0:
                raise ValueError("Uploaded file is empty")
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            await upload.close()
        return StoredDocument(path=target, sha256=digest.hexdigest(), byte_size=size)

    def delete(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        directory = self._document_directory(user_id, document_id)
        if directory.is_relative_to(self.root):
            shutil.rmtree(directory, ignore_errors=True)

    def _document_directory(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Path:
        directory = (self.root / str(user_id) / str(document_id)).resolve()
        if not directory.is_relative_to(self.root):
            raise ValueError("Invalid document storage path")
        return directory
