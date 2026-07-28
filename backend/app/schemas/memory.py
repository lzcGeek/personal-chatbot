from uuid import UUID

from pydantic import BaseModel


class MemoryConfirmation(BaseModel):
    replace_memory_id: UUID | None = None
