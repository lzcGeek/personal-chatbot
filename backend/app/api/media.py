import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.character import Character
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.media_task import MediaTask
from app.models.message_attachment import MessageAttachment
from app.models.user import User
from app.schemas.media import MediaGenerationRequest
from app.services.auth_dependencies import get_current_user


router = APIRouter(prefix="/api/media", tags=["media"])


def serialize_task(task: MediaTask) -> dict[str, object]:
    return {
        "id": str(task.id), "message_id": task.message_id, "kind": task.kind,
        "profile_id": task.profile_id, "status": task.status, "attempts": task.attempts,
        "error_code": task.error_code, "error_message": task.error_message,
        "created_at": task.created_at.isoformat(), "updated_at": task.updated_at.isoformat(),
    }


def serialize_attachment(item: MessageAttachment) -> dict[str, object]:
    return {
        "id": str(item.id), "message_id": item.message_id, "task_id": str(item.task_id),
        "kind": item.kind, "mime_type": item.mime_type, "byte_size": item.byte_size,
        "provider_id": item.provider_id, "profile_id": item.profile_id,
        "download_url": f"/api/media/attachments/{item.id}",
        "created_at": item.created_at.isoformat(),
    }


@router.get("/capabilities")
async def media_capabilities(request: Request, user: User = Depends(get_current_user)) -> dict[str, object]:
    return request.app.state.media_registry.capabilities()


@router.post("/messages/{message_id}/{kind}", status_code=status.HTTP_202_ACCEPTED)
async def create_media_task(
    message_id: int,
    kind: str,
    payload: MediaGenerationRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    if kind not in {"image", "tts"}:
        raise HTTPException(status_code=404, detail="Unsupported media kind")
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(MediaTask).where(
                MediaTask.user_id == user.id,
                MediaTask.idempotency_key == payload.idempotency_key,
                MediaTask.kind == kind,
            )
        )
        if existing is not None:
            return serialize_task(existing)
        row = (
            await session.execute(
                select(ChatMessage, Character)
                .join(Conversation, Conversation.id == ChatMessage.conversation_id)
                .outerjoin(Character, Character.id == ChatMessage.character_id)
                .where(
                    ChatMessage.id == message_id,
                    ChatMessage.role == "assistant",
                    ChatMessage.status == "complete",
                    Conversation.user_id == user.id,
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Message not found")
        message, character = row
        if character is not None and not bool(character.permissions.get(kind)):
            raise HTTPException(status_code=403, detail=f"Character does not allow {kind} generation")
        default_profile = None
        if character is not None:
            default_profile = character.image_profile_id if kind == "image" else character.tts_profile_id
        try:
            _, profile = request.app.state.media_registry.resolve(kind, payload.profile_id or default_profile)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        active_count = await session.scalar(
            select(func.count(MediaTask.id)).where(
                MediaTask.user_id == user.id,
                MediaTask.message_id == message_id,
                MediaTask.kind == kind,
                MediaTask.status != "failed",
            )
        )
        if active_count >= request.app.state.media_registry.max_tasks_per_message:
            raise HTTPException(status_code=429, detail="Media generation limit reached")
        input_text = message.content if kind == "tts" else (
            payload.prompt or f"Create a roleplay illustration for this message:\n{message.content}"
        )
        task = MediaTask(
            user_id=user.id,
            conversation_id=message.conversation_id,
            message_id=message.id,
            character_id=message.character_id,
            kind=kind,
            profile_id=profile,
            input_text=input_text,
            idempotency_key=payload.idempotency_key,
        )
        session.add(task)
        try:
            await session.commit()
            await session.refresh(task)
        except IntegrityError:
            await session.rollback()
            task = await session.scalar(
                select(MediaTask).where(
                    MediaTask.user_id == user.id,
                    MediaTask.idempotency_key == payload.idempotency_key,
                    MediaTask.kind == kind,
                )
            )
            if task is None:
                raise
        return serialize_task(task)


@router.get("/tasks/{task_id}")
async def get_media_task(task_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict[str, object]:
    async with SessionLocal() as session:
        task = await session.scalar(select(MediaTask).where(MediaTask.id == task_id, MediaTask.user_id == user.id))
        if task is None:
            raise HTTPException(status_code=404, detail="Media task not found")
        return serialize_task(task)


@router.post("/tasks/{task_id}/retry")
async def retry_media_task(task_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict[str, object]:
    async with SessionLocal() as session:
        task = await session.scalar(select(MediaTask).where(MediaTask.id == task_id, MediaTask.user_id == user.id))
        if task is None or task.status != "failed":
            raise HTTPException(status_code=404, detail="Retryable media task not found")
        task.status = "pending"
        task.attempts = 0
        task.error_code = None
        task.error_message = None
        await session.commit()
        await session.refresh(task)
        return serialize_task(task)


@router.get("/tasks/{task_id}/events")
async def media_task_events(task_id: uuid.UUID, user: User = Depends(get_current_user)) -> StreamingResponse:
    async def events():
        last_status = None
        while True:
            async with SessionLocal() as session:
                task = await session.scalar(select(MediaTask).where(MediaTask.id == task_id, MediaTask.user_id == user.id))
                if task is None:
                    yield 'event: media_status\ndata: {"status":"not_found"}\n\n'
                    return
                if task.status != last_status:
                    yield f"event: media_status\ndata: {json.dumps(serialize_task(task))}\n\n"
                    last_status = task.status
                if task.status in {"complete", "failed"}:
                    return
            await asyncio.sleep(0.5)
    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/messages/{message_id}/attachments")
async def list_message_attachments(message_id: int, user: User = Depends(get_current_user)) -> dict[str, object]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(MessageAttachment)
            .join(Conversation, Conversation.id == MessageAttachment.conversation_id)
            .where(MessageAttachment.message_id == message_id, Conversation.user_id == user.id)
            .order_by(MessageAttachment.created_at)
        )
        return {"attachments": [serialize_attachment(item) for item in rows.scalars()]}


@router.get("/attachments/{attachment_id}")
async def download_attachment(attachment_id: uuid.UUID, request: Request, user: User = Depends(get_current_user)) -> FileResponse:
    async with SessionLocal() as session:
        item = await session.scalar(
            select(MessageAttachment).where(
                MessageAttachment.id == attachment_id, MessageAttachment.user_id == user.id
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Attachment not found")
        try:
            path = request.app.state.media_storage.validate_owned_path(
                item.storage_path, user.id, item.conversation_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Attachment not found") from exc
        return FileResponse(path, media_type=item.mime_type)


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(attachment_id: uuid.UUID, request: Request, user: User = Depends(get_current_user)) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            item = await session.scalar(
                select(MessageAttachment).where(
                    MessageAttachment.id == attachment_id, MessageAttachment.user_id == user.id
                )
            )
            if item is None:
                raise HTTPException(status_code=404, detail="Attachment not found")
            path = item.storage_path
            await session.delete(item)
    await asyncio.to_thread(request.app.state.media_storage.delete_file, path)
