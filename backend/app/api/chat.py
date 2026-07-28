import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.auth_dependencies import get_current_user
from app.services.chat_service import ChatService
from app.services.chat_errors import ChatFailure, classify_chat_failure


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/send")
async def send_chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")
    try:
        message = await request.app.state.chat_service.send(
            payload.message,
            user.id,
            payload.conversation_id,
            allow_network=payload.allow_network,
            client_request_id=payload.client_request_id,
            target_character_id=payload.target_character_id,
            max_speakers=payload.max_speakers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChatFailure as exc:
        raise HTTPException(status_code=503 if exc.recoverable else 422, detail=exc.user_message) from exc
    except Exception as exc:
        failure = classify_chat_failure(exc)
        raise HTTPException(status_code=503, detail=failure.user_message) from exc
    return {"message": ChatService.serialize_message(message)}


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")

    async def events():
        async for event in request.app.state.chat_service.stream(
            payload.message,
            user.id,
            payload.conversation_id,
            allow_network=payload.allow_network,
            client_request_id=payload.client_request_id,
            target_character_id=payload.target_character_id,
            max_speakers=payload.max_speakers,
        ):
            event_type = event.pop("type")
            yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
async def chat_history(
    conversation_id: uuid.UUID,
    before_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    async with SessionLocal() as session:
        owned = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        statement = select(ChatMessage).where(
            ChatMessage.conversation_id == conversation_id
        )
        if before_id is not None:
            statement = statement.where(ChatMessage.id < before_id)
        result = await session.execute(
            statement.order_by(ChatMessage.id.desc()).limit(limit + 1)
        )
        rows = list(result.scalars())
    has_more = len(rows) > limit
    messages = list(reversed(rows[:limit]))
    return {
        "messages": [ChatService.serialize_message(message) for message in messages],
        "has_more": has_more,
        "next_before_id": messages[0].id if has_more and messages else None,
    }
