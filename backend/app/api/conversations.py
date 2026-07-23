from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.memory_entry import MemoryEntry

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def serialize(conv: Conversation) -> dict[str, object]:
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@router.get("")
async def list_conversations() -> dict[str, list[dict[str, object]]]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Conversation).order_by(Conversation.updated_at.desc())
        )
        conversations = list(result.scalars())
    return {"conversations": [serialize(conv) for conv in conversations]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(request: Request) -> dict[str, object]:
    async with SessionLocal() as session:
        conv = Conversation(title="新对话")
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
    return serialize(conv)


@router.patch("/{conv_id}")
async def rename_conversation(conv_id: int, request: Request) -> dict[str, object]:
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title must not be empty")
    async with SessionLocal() as session:
        conv = await session.get(Conversation, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv.title = title
        await session.commit()
        await session.refresh(conv)
    return serialize(conv)


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conv_id: int, request: Request) -> None:
    async with SessionLocal() as session:
        conv = await session.get(Conversation, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Prevent deleting last conversation: auto-create new one first
        count = (await session.execute(select(Conversation))).scalars().all()
        if len(count) <= 1:
            new_conv = Conversation(title="新对话")
            session.add(new_conv)
            await session.flush()

        # Cascade delete messages and memories (SQLite FK handles this)
        await session.delete(conv)
        await session.commit()

    # Clean up ChromaDB vectors for deleted conversation
    if request.app.state.memory_service:
        await request.app.state.memory_service.delete_by_conversation(conv_id)
