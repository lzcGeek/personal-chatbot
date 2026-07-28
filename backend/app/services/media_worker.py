import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.media_task import MediaTask
from app.models.message_attachment import MessageAttachment
from app.services.media_providers import MediaCapabilityRegistry
from app.services.media_storage import MediaStorage
from app.services.observability import log_background_job


logger = logging.getLogger(__name__)


class MediaWorker:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], registry: MediaCapabilityRegistry, storage: MediaStorage, poll_seconds: float, max_attempts: int) -> None:
        self.session_factory = session_factory
        self.registry = registry
        self.storage = storage
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="media-worker")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                processed = await self._process_one()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Media worker iteration failed")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_seconds)

    async def _process_one(self) -> bool:
        async with self.session_factory() as session:
            async with session.begin():
                task = await session.scalar(
                    select(MediaTask)
                    .where(MediaTask.status == "pending", MediaTask.next_retry_at <= datetime.now(timezone.utc))
                    .order_by(MediaTask.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if task is None:
                    return False
                task.status = "processing"
                task_id = task.id
        try:
            await self._complete(task_id)
        except Exception as exc:
            await self._fail(task_id, exc)
        return True

    async def _complete(self, task_id) -> None:
        async with self.session_factory() as session:
            task = await session.get(MediaTask, task_id)
            if task is None:
                return
            provider, profile = self.registry.resolve(task.kind, task.profile_id)
            media = await provider.generate(task.input_text, profile)
            attachment = MessageAttachment(
                user_id=task.user_id,
                conversation_id=task.conversation_id,
                message_id=task.message_id,
                task_id=task.id,
                kind=task.kind,
                mime_type=media.mime_type,
                byte_size=len(media.content),
                storage_path="",
                provider_id=task.provider_id,
                profile_id=profile,
            )
            path = await asyncio.to_thread(
                self.storage.save, media, task.user_id, task.conversation_id, attachment.id
            )
            attachment.storage_path = str(path)
            session.add(attachment)
            task.status = "complete"
            task.error_code = None
            task.error_message = None
            try:
                await session.commit()
                log_background_job(f"media.{task.kind}", "complete")
            except Exception:
                await asyncio.to_thread(self.storage.delete_file, str(path))
                raise

    async def _fail(self, task_id, exc: Exception) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                task = await session.get(MediaTask, task_id, with_for_update=True)
                if task is None:
                    return
                task.attempts += 1
                task.error_code = "media_generation_failed"
                task.error_message = str(exc)[:500] if isinstance(exc, ValueError) else "Provider request failed"
                if task.attempts >= self.max_attempts:
                    task.status = "failed"
                else:
                    task.status = "pending"
                    task.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=2 ** task.attempts)
        log_background_job(f"media.{task.kind}", "failed" if task.status == "failed" else "retry")
