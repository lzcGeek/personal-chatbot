import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.character import Character
from app.models.user import User
from app.schemas.character import CharacterCreate, CharacterInfo, CharacterUpdate
from app.services.auth_dependencies import get_current_user


router = APIRouter(prefix="/api/characters", tags=["characters"])


def serialize(character: Character) -> CharacterInfo:
    return CharacterInfo(
        id=character.id,
        name=character.name,
        description=character.description,
        personality=character.personality,
        scenario=character.scenario,
        greeting=character.greeting,
        example_dialogue=character.example_dialogue,
        generation_settings=character.generation_settings,
        permissions=character.permissions,
        image_profile_id=character.image_profile_id,
        tts_profile_id=character.tts_profile_id,
        archived=character.archived,
        has_avatar=bool(character.avatar_path),
        created_at=character.created_at,
        updated_at=character.updated_at,
    )


async def owned_character(character_id: uuid.UUID, user_id: uuid.UUID) -> Character | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(Character).where(
                Character.id == character_id,
                Character.user_id == user_id,
                Character.deleted_at.is_(None),
            )
        )


@router.get("", response_model=list[CharacterInfo])
async def list_characters(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
) -> list[CharacterInfo]:
    async with SessionLocal() as session:
        statement = select(Character).where(
            Character.user_id == user.id, Character.deleted_at.is_(None)
        )
        if not include_archived:
            statement = statement.where(Character.archived.is_(False))
        rows = await session.execute(statement.order_by(Character.updated_at.desc()))
        return [serialize(item) for item in rows.scalars()]


@router.post("", response_model=CharacterInfo, status_code=status.HTTP_201_CREATED)
async def create_character(
    payload: CharacterCreate, user: User = Depends(get_current_user)
) -> CharacterInfo:
    character = Character(user_id=user.id, **payload.model_dump())
    async with SessionLocal() as session:
        session.add(character)
        await session.commit()
        await session.refresh(character)
    return serialize(character)


@router.get("/{character_id}", response_model=CharacterInfo)
async def get_character(
    character_id: uuid.UUID, user: User = Depends(get_current_user)
) -> CharacterInfo:
    character = await owned_character(character_id, user.id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return serialize(character)


@router.put("/{character_id}", response_model=CharacterInfo)
async def update_character(
    character_id: uuid.UUID,
    payload: CharacterUpdate,
    user: User = Depends(get_current_user),
) -> CharacterInfo:
    async with SessionLocal() as session:
        character = await session.scalar(
            select(Character).where(
                Character.id == character_id,
                Character.user_id == user.id,
                Character.deleted_at.is_(None),
            )
        )
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found")
        for key, value in payload.model_dump().items():
            setattr(character, key, value)
        await session.commit()
        await session.refresh(character)
    return serialize(character)


@router.post("/{character_id}/duplicate", response_model=CharacterInfo, status_code=201)
async def duplicate_character(
    character_id: uuid.UUID, user: User = Depends(get_current_user)
) -> CharacterInfo:
    source = await owned_character(character_id, user.id)
    if source is None:
        raise HTTPException(status_code=404, detail="Character not found")
    duplicate = Character(
        user_id=user.id,
        name=f"{source.name} 副本"[:120],
        description=source.description,
        personality=source.personality,
        scenario=source.scenario,
        greeting=source.greeting,
        example_dialogue=source.example_dialogue,
        generation_settings=dict(source.generation_settings),
        permissions=dict(source.permissions),
        image_profile_id=source.image_profile_id,
        tts_profile_id=source.tts_profile_id,
    )
    async with SessionLocal() as session:
        session.add(duplicate)
        await session.commit()
        await session.refresh(duplicate)
    return serialize(duplicate)


@router.delete("/{character_id}", status_code=204)
async def delete_character(
    character_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    async with SessionLocal() as session:
        character = await session.scalar(
            select(Character).where(
                Character.id == character_id,
                Character.user_id == user.id,
                Character.deleted_at.is_(None),
            )
        )
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found")
        character.archived = True
        character.deleted_at = datetime.now(timezone.utc)
        character.avatar_path = None
        await session.commit()
    await asyncio.to_thread(request.app.state.avatar_storage.delete, user.id, character_id)


@router.post("/{character_id}/avatar", response_model=CharacterInfo)
async def upload_avatar(
    character_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> CharacterInfo:
    character = await owned_character(character_id, user.id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    try:
        path = await request.app.state.avatar_storage.save(file, user.id, character_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    async with SessionLocal() as session:
        stored = await session.scalar(
            select(Character).where(
                Character.id == character_id,
                Character.user_id == user.id,
                Character.deleted_at.is_(None),
            )
        )
        if stored is None:
            await asyncio.to_thread(request.app.state.avatar_storage.delete, user.id, character_id)
            raise HTTPException(status_code=404, detail="Character not found")
        stored.avatar_path = str(path)
        await session.commit()
        await session.refresh(stored)
    return serialize(stored)


@router.get("/{character_id}/avatar")
async def get_avatar(
    character_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> FileResponse:
    character = await owned_character(character_id, user.id)
    if character is None or character.avatar_path is None:
        raise HTTPException(status_code=404, detail="Avatar not found")
    try:
        path = request.app.state.avatar_storage.validate_owned_path(
            character.avatar_path, user.id, character.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Avatar not found") from exc
    return FileResponse(path)
