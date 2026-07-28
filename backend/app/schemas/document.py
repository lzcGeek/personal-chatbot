from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


GraphMode = Literal["inherit", "enabled", "disabled"]


class DocumentInfo(BaseModel):
    id: UUID
    filename: str
    media_type: str
    byte_size: int
    status: str
    processing_phase: str
    graph_mode: GraphMode
    graph_status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class GraphBuildRequest(BaseModel):
    rebuild: bool = False
