import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.models.user import User
from app.schemas.memory import MemoryConfirmation
from app.services.auth_dependencies import get_current_user


router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("")
async def list_memories(
    request: Request,
    conversation_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> dict[str, list[dict[str, object]]]:
    entries = await request.app.state.memory_service.list_entries(user.id, conversation_id)
    return {
        "memories": [
            {
                "id": str(entry.id),
                "conversation_id": str(entry.conversation_id),
                "content": entry.content,
                "source_message_ids": entry.source_message_ids,
                "metadata": entry.metadata_json,
                "importance": entry.importance,
                "scope": entry.scope,
                "character_id": str(entry.character_id) if entry.character_id else None,
                "validity": entry.validity,
                "superseded_by_id": (
                    str(entry.superseded_by_id) if entry.superseded_by_id else None
                ),
                "conflict_reason": entry.conflict_reason,
                "effective_from": (
                    entry.effective_from.isoformat() if entry.effective_from else None
                ),
                "effective_to": entry.effective_to.isoformat() if entry.effective_to else None,
                "embedding_status": entry.embedding_status,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]
    }


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    entry_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    deleted = await request.app.state.memory_service.delete_entry(entry_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")


@router.post("/{entry_id}/invalidate")
async def invalidate_memory(
    entry_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    entry = await request.app.state.memory_service.set_validity(
        entry_id, user.id, "invalid"
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"id": str(entry.id), "validity": entry.validity}


@router.post("/{entry_id}/restore")
async def restore_memory(
    entry_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    entry = await request.app.state.memory_service.set_validity(entry_id, user.id, "active")
    if entry is None:
        raise HTTPException(status_code=404, detail="Restorable memory entry not found")
    return {"id": str(entry.id), "validity": entry.validity}


@router.post("/{entry_id}/confirm")
async def confirm_memory(
    entry_id: uuid.UUID,
    payload: MemoryConfirmation,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    entry = await request.app.state.memory_service.confirm_candidate(
        entry_id, user.id, payload.replace_memory_id
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Confirmable memory entry not found")
    return {"id": str(entry.id), "validity": entry.validity}
