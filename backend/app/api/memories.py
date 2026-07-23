from fastapi import APIRouter, HTTPException, Request, status


router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("")
async def list_memories(request: Request) -> dict[str, list[dict[str, object]]]:
    entries = await request.app.state.memory_service.list_entries()
    return {
        "memories": [
            {
                "id": entry.id,
                "content": entry.content,
                "source_message_ids": entry.source_message_ids,
                "metadata": entry.metadata_json,
                "importance": entry.importance,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]
    }


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(entry_id: int, request: Request) -> None:
    deleted = await request.app.state.memory_service.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
