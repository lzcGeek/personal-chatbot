import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models.character import Character
from app.models.conversation import Conversation
from app.models.conversation_member import ConversationMember
from app.models.conversation_state import ConversationState
from app.models.conversation_summary import ConversationSummary
from app.models.user import User
from app.schemas.character import ConversationMemberInfo
from app.schemas.conversation import (
    ConversationMembersUpdate,
    ConversationSettingsUpdate,
    ConversationStateUpdate,
)
from app.services.auth_dependencies import get_current_user
from app.services.memory_service import MemoryService


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def serialize_summary(summary: ConversationSummary) -> dict[str, object]:
    return {
        "id": str(summary.id),
        "conversation_id": str(summary.conversation_id),
        "start_message_id": summary.start_message_id,
        "end_message_id": summary.end_message_id,
        "version": summary.version,
        "status": summary.status,
        "content": summary.content,
        "error_message": summary.error_message,
        "created_at": summary.created_at.isoformat(),
        "updated_at": summary.updated_at.isoformat(),
    }


def serialize(conv: Conversation) -> dict[str, object]:
    return {
        "id": str(conv.id),
        "title": conv.title,
        "retrieval_mode": conv.retrieval_mode,
        "mode": conv.mode,
        "routing_strategy": conv.routing_strategy,
        "scene_description": conv.scene_description,
        "max_speakers_per_turn": conv.max_speakers_per_turn,
        "max_group_generations": conv.max_group_generations,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@router.get("")
async def list_conversations(
    user: User = Depends(get_current_user),
) -> dict[str, list[dict[str, object]]]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        )
        conversations = list(result.scalars())
    return {"conversations": [serialize(conv) for conv in conversations]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    async with SessionLocal() as session:
        conv = Conversation(title="新对话", user_id=user.id)
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
    return serialize(conv)


@router.patch("/{conv_id}/settings")
async def update_conversation_settings(
    conv_id: uuid.UUID,
    payload: ConversationSettingsUpdate,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    async with SessionLocal() as session:
        conv = (
            await session.execute(
                select(Conversation).where(
                    Conversation.id == conv_id,
                    Conversation.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        updates = payload.model_dump(exclude_none=True)
        requested_mode = updates.get("mode", conv.mode)
        if requested_mode in {"single_character", "group"}:
            enabled_members = await session.scalar(
                select(func.count(ConversationMember.id)).where(
                    ConversationMember.conversation_id == conv.id,
                    ConversationMember.user_id == user.id,
                    ConversationMember.enabled.is_(True),
                )
            )
            if not enabled_members:
                raise HTTPException(
                    status_code=422, detail="NPC conversation requires an enabled member"
                )
            if requested_mode == "single_character" and enabled_members != 1:
                raise HTTPException(
                    status_code=422, detail="Single-character mode requires exactly one member"
                )
        for key, value in updates.items():
            setattr(conv, key, value)
        await session.commit()
        await session.refresh(conv)
    return serialize(conv)


@router.get("/{conv_id}/members", response_model=list[ConversationMemberInfo])
async def list_conversation_members(
    conv_id: uuid.UUID, user: User = Depends(get_current_user)
) -> list[ConversationMemberInfo]:
    async with SessionLocal() as session:
        owned = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == conv_id, Conversation.user_id == user.id
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        rows = await session.execute(
            select(ConversationMember, Character)
            .join(Character, Character.id == ConversationMember.character_id)
            .where(
                ConversationMember.conversation_id == conv_id,
                ConversationMember.user_id == user.id,
                Character.deleted_at.is_(None),
            )
            .order_by(ConversationMember.position, ConversationMember.id)
        )
        return [
            ConversationMemberInfo(
                id=member.id,
                character_id=member.character_id,
                position=member.position,
                enabled=member.enabled,
                overrides=member.overrides,
                name=character.name,
            )
            for member, character in rows.all()
        ]


@router.put("/{conv_id}/members", response_model=list[ConversationMemberInfo])
async def replace_conversation_members(
    conv_id: uuid.UUID,
    payload: ConversationMembersUpdate,
    user: User = Depends(get_current_user),
) -> list[ConversationMemberInfo]:
    async with SessionLocal() as session:
        async with session.begin():
            conv = await session.scalar(
                select(Conversation)
                .where(Conversation.id == conv_id, Conversation.user_id == user.id)
                .with_for_update()
            )
            if conv is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            character_ids = {item.character_id for item in payload.members}
            if character_ids:
                rows = await session.execute(
                    select(Character.id).where(
                        Character.id.in_(character_ids),
                        Character.user_id == user.id,
                        Character.deleted_at.is_(None),
                        Character.archived.is_(False),
                    )
                )
                if set(rows.scalars()) != character_ids:
                    raise HTTPException(status_code=404, detail="Character not found")
            enabled_count = sum(item.enabled for item in payload.members)
            if conv.mode == "group" and enabled_count < 1:
                raise HTTPException(status_code=422, detail="Group mode requires a member")
            if conv.mode == "single_character" and enabled_count != 1:
                raise HTTPException(
                    status_code=422, detail="Single-character mode requires exactly one member"
                )
            await session.execute(
                delete(ConversationMember).where(
                    ConversationMember.conversation_id == conv.id,
                    ConversationMember.user_id == user.id,
                )
            )
            session.add_all(
                [
                    ConversationMember(
                        user_id=user.id,
                        conversation_id=conv.id,
                        **item.model_dump(),
                    )
                    for item in payload.members
                ]
            )
    return await list_conversation_members(conv_id, user)


@router.get("/{conv_id}/state")
async def get_conversation_state(
    conv_id: uuid.UUID, user: User = Depends(get_current_user)
) -> dict[str, object]:
    async with SessionLocal() as session:
        owned = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == conv_id, Conversation.user_id == user.id
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        state = await session.get(ConversationState, conv_id)
        if state is None:
            return {"conversation_id": str(conv_id), "state": {}, "revision": 0, "source_message_ids": []}
        return {
            "conversation_id": str(conv_id),
            "state": state.state_json,
            "revision": state.revision,
            "source_message_ids": state.source_message_ids,
        }


@router.put("/{conv_id}/state")
async def update_conversation_state(
    conv_id: uuid.UUID,
    payload: ConversationStateUpdate,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    async with SessionLocal() as session:
        async with session.begin():
            owned = await session.scalar(
                select(Conversation.id)
                .where(Conversation.id == conv_id, Conversation.user_id == user.id)
                .with_for_update()
            )
            if owned is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            state = await session.get(ConversationState, conv_id, with_for_update=True)
            current_revision = state.revision if state is not None else 0
            if current_revision != payload.expected_revision:
                raise HTTPException(status_code=409, detail="Scene state revision conflict")
            if state is None:
                state = ConversationState(
                    conversation_id=conv_id,
                    user_id=user.id,
                    state_json=payload.state,
                    revision=1,
                    source_message_ids=payload.source_message_ids,
                )
                session.add(state)
            else:
                state.state_json = payload.state
                state.source_message_ids = payload.source_message_ids
                state.revision += 1
        await session.refresh(state)
        return {
            "conversation_id": str(conv_id),
            "state": state.state_json,
            "revision": state.revision,
            "source_message_ids": state.source_message_ids,
        }


@router.get("/{conv_id}/summaries")
async def list_conversation_summaries(
    conv_id: uuid.UUID, user: User = Depends(get_current_user)
) -> dict[str, list[dict[str, object]]]:
    async with SessionLocal() as session:
        owned = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == conv_id, Conversation.user_id == user.id
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        rows = await session.execute(
            select(ConversationSummary)
            .where(
                ConversationSummary.conversation_id == conv_id,
                ConversationSummary.user_id == user.id,
            )
            .order_by(
                ConversationSummary.start_message_id.desc(),
                ConversationSummary.version.desc(),
            )
        )
        return {"summaries": [serialize_summary(item) for item in rows.scalars()]}


@router.post("/{conv_id}/summaries/{summary_id}/regenerate", status_code=202)
async def regenerate_conversation_summary(
    conv_id: uuid.UUID,
    summary_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    if not request.app.state.settings.memory_compression_enabled:
        raise HTTPException(status_code=503, detail="Memory compression is disabled")
    async with SessionLocal() as session:
        summary = await session.scalar(
            select(ConversationSummary).where(
                ConversationSummary.id == summary_id,
                ConversationSummary.conversation_id == conv_id,
                ConversationSummary.user_id == user.id,
            )
        )
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    queued = await request.app.state.compression_service.enqueue_range(
        user.id,
        conv_id,
        summary.start_message_id,
        summary.end_message_id,
    )
    if not queued:
        raise HTTPException(status_code=409, detail="Summary regeneration already queued")
    return {"queued": True, "start_message_id": summary.start_message_id, "end_message_id": summary.end_message_id}


@router.delete("/{conv_id}/summaries/{summary_id}", status_code=204)
async def delete_conversation_summary(
    conv_id: uuid.UUID,
    summary_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            summary = await session.scalar(
                select(ConversationSummary).where(
                    ConversationSummary.id == summary_id,
                    ConversationSummary.conversation_id == conv_id,
                    ConversationSummary.user_id == user.id,
                )
            )
            if summary is None:
                raise HTTPException(status_code=404, detail="Summary not found")
            await session.delete(summary)


@router.patch("/{conv_id}")
async def rename_conversation(
    conv_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title must not be empty")
    async with SessionLocal() as session:
        conv = (
            await session.execute(
                select(Conversation).where(
                    Conversation.id == conv_id,
                    Conversation.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv.title = title[:200]
        await session.commit()
        await session.refresh(conv)
    return serialize(conv)


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conv_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            conv = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.id == conv_id,
                        Conversation.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
            if conv is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            count = await session.scalar(
                select(func.count(Conversation.id)).where(Conversation.user_id == user.id)
            )
            if count <= 1:
                session.add(Conversation(title="新对话", user_id=user.id))
            MemoryService.enqueue_conversation_delete(session, user.id, conv_id)
            await session.delete(conv)
    media_storage = getattr(request.app.state, "media_storage", None)
    if media_storage is not None:
        await asyncio.to_thread(
            media_storage.delete_conversation, user.id, conv_id
        )
