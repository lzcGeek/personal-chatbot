import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.chat_message import ChatMessage
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/send")
async def send_chat(payload: ChatRequest, request: Request) -> dict[str, object]:
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")
    message = await request.app.state.chat_service.send(payload.message, payload.conversation_id)
    return {"message": ChatService.serialize_message(message)}


@router.post("/stream")
async def stream_chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")

    async def events():
        async for event in request.app.state.chat_service.stream(payload.message, payload.conversation_id):
            event_type = event.pop("type")
            yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
async def chat_history(
    before_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    conversation_id: int | None = Query(default=None),
) -> dict[str, object]:
    async with SessionLocal() as session:
        statement = select(ChatMessage)
        if conversation_id is not None:
            statement = statement.where(ChatMessage.conversation_id == conversation_id)
        if before_id is not None:
            statement = statement.where(ChatMessage.id < before_id)
        result = await session.execute(statement.order_by(ChatMessage.id.desc()).limit(limit + 1))
        rows = list(result.scalars())
    has_more = len(rows) > limit
    messages = list(reversed(rows[:limit]))
    return {
        "messages": [ChatService.serialize_message(message) for message in messages],
        "has_more": has_more,
        "next_before_id": messages[0].id if has_more and messages else None,
    }
