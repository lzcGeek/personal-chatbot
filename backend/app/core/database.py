from collections.abc import AsyncIterator
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.debug)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_database() -> None:
    from app import models  # noqa: F401
    from app.models.mcp_server import migrate_enabled_column

    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys = ON"))
        await connection.run_sync(Base.metadata.create_all)
    await migrate_enabled_column()
    await _migrate_conversations()


async def _migrate_conversations() -> None:
    """Add conversation_id columns and assign legacy data to a default conversation."""
    async with engine.begin() as connection:
        for table in ("chat_messages", "memory_entries"):
            try:
                await connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN conversation_id INTEGER REFERENCES conversations(id)")
                )
            except Exception:
                logger.debug("conversation_id column already exists in %s", table)

        # Create default conversation if none exist
        result = await connection.execute(text("SELECT COUNT(*) FROM conversations"))
        if result.scalar() == 0:
            await connection.execute(
                text("INSERT INTO conversations (title, created_at, updated_at) VALUES ('默认会话', datetime('now'), datetime('now'))")
            )
        result = await connection.execute(text("SELECT id FROM conversations LIMIT 1"))
        default_id = result.scalar()

        # Assign orphan messages
        await connection.execute(
            text("UPDATE chat_messages SET conversation_id = :cid WHERE conversation_id IS NULL"),
            {"cid": default_id},
        )
        await connection.execute(
            text("UPDATE memory_entries SET conversation_id = :cid WHERE conversation_id IS NULL"),
            {"cid": default_id},
        )



async def close_database() -> None:
    await engine.dispose()
