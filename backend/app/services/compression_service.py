import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.chat_message import ChatMessage
from app.models.compression_job import CompressionJob
from app.models.conversation_summary import ConversationSummary
from app.services.llm_client import LlmClient
from app.services.observability import log_background_job


logger = logging.getLogger(__name__)


class CompressionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_client: LlmClient,
        trigger_messages: int,
        keep_recent: int,
        poll_seconds: float,
        max_attempts: int,
    ) -> None:
        self.session_factory = session_factory
        self.llm_client = llm_client
        self.trigger_messages = trigger_messages
        self.keep_recent = keep_recent
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="conversation-compression-worker")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def enqueue_if_needed(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        async with self.session_factory() as session:
            last_end = await session.scalar(
                select(func.max(ConversationSummary.end_message_id)).where(
                    ConversationSummary.user_id == user_id,
                    ConversationSummary.conversation_id == conversation_id,
                    ConversationSummary.status == "complete",
                )
            ) or 0
            ids = list(
                (
                    await session.execute(
                        select(ChatMessage.id)
                        .where(
                            ChatMessage.conversation_id == conversation_id,
                            ChatMessage.id > last_end,
                            ChatMessage.status == "complete",
                        )
                        .order_by(ChatMessage.id)
                    )
                ).scalars()
            )
            selected = self._select_range(ids, self.trigger_messages, self.keep_recent)
            if selected is None:
                return False
            start_id, end_id = selected
            active = await session.scalar(
                select(CompressionJob.id).where(
                    CompressionJob.user_id == user_id,
                    CompressionJob.conversation_id == conversation_id,
                    CompressionJob.start_message_id == start_id,
                    CompressionJob.end_message_id == end_id,
                    CompressionJob.status.in_(("pending", "processing")),
                )
            )
            if active is not None:
                return False
            session.add(
                CompressionJob(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    start_message_id=start_id,
                    end_message_id=end_id,
                )
            )
            await session.commit()
            log_background_job("compression", "queued")
            return True

    async def enqueue_range(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        start_message_id: int,
        end_message_id: int,
    ) -> bool:
        """Queue an owner-validated range for summary regeneration."""
        async with self.session_factory() as session:
            ids = list(
                (
                    await session.execute(
                        select(ChatMessage.id)
                        .where(
                            ChatMessage.conversation_id == conversation_id,
                            ChatMessage.id >= start_message_id,
                            ChatMessage.id <= end_message_id,
                            ChatMessage.status == "complete",
                        )
                        .order_by(ChatMessage.id)
                    )
                ).scalars()
            )
            if not ids or ids[0] != start_message_id or ids[-1] != end_message_id:
                return False
            active = await session.scalar(
                select(CompressionJob.id).where(
                    CompressionJob.user_id == user_id,
                    CompressionJob.conversation_id == conversation_id,
                    CompressionJob.start_message_id == start_message_id,
                    CompressionJob.end_message_id == end_message_id,
                    CompressionJob.status.in_(("pending", "processing")),
                )
            )
            if active is not None:
                return False
            session.add(
                CompressionJob(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    start_message_id=start_message_id,
                    end_message_id=end_message_id,
                )
            )
            await session.commit()
            log_background_job("compression", "queued")
            return True

    @staticmethod
    def _select_range(
        message_ids: list[int], trigger_messages: int, keep_recent: int
    ) -> tuple[int, int] | None:
        if len(message_ids) < trigger_messages or len(message_ids) <= keep_recent:
            return None
        return message_ids[0], message_ids[-keep_recent - 1]

    async def _run(self) -> None:
        while True:
            try:
                processed = await self._process_one()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Compression worker iteration failed")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_seconds)

    async def _process_one(self) -> bool:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                job = (
                    await session.execute(
                        select(CompressionJob)
                        .where(
                            CompressionJob.status == "pending",
                            CompressionJob.next_retry_at <= now,
                        )
                        .order_by(CompressionJob.id)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if job is None:
                    return False
                job.status = "processing"
                job_id = job.id
        try:
            await self._complete_job(job_id)
        except Exception as exc:
            await self._fail_job(job_id, exc)
        return True

    async def _complete_job(self, job_id: int) -> None:
        async with self.session_factory() as session:
            job = await session.get(CompressionJob, job_id)
            if job is None:
                return
            rows = await session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.conversation_id == job.conversation_id,
                    ChatMessage.id >= job.start_message_id,
                    ChatMessage.id <= job.end_message_id,
                    ChatMessage.status == "complete",
                )
                .order_by(ChatMessage.id)
            )
            messages = list(rows.scalars())
            if not messages or messages[0].id != job.start_message_id or messages[-1].id != job.end_message_id:
                raise ValueError("Compression range is no longer contiguous")
            content = await self.llm_client.summarize_messages(
                [{"role": item.role, "content": item.content} for item in messages]
            )
            if not content.strip():
                raise ValueError("Summary was empty")
            version = 1 + (await session.scalar(
                select(func.max(ConversationSummary.version)).where(
                    ConversationSummary.conversation_id == job.conversation_id
                )
            ) or 0)
            async with session.begin_nested():
                session.add(
                    ConversationSummary(
                        user_id=job.user_id,
                        conversation_id=job.conversation_id,
                        start_message_id=job.start_message_id,
                        end_message_id=job.end_message_id,
                        version=version,
                        status="complete",
                        content=content.strip(),
                    )
                )
                job.status = "done"
                job.last_error = None
            await session.commit()
            log_background_job("compression", "complete")

    async def _fail_job(self, job_id: int, exc: Exception) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.get(CompressionJob, job_id, with_for_update=True)
                if job is None:
                    return
                job.attempts += 1
                job.last_error = (str(exc) or exc.__class__.__name__)[:4000]
                if job.attempts >= self.max_attempts:
                    job.status = "failed"
                    version = 1 + (await session.scalar(
                        select(func.max(ConversationSummary.version)).where(
                            ConversationSummary.conversation_id == job.conversation_id
                        )
                    ) or 0)
                    session.add(
                        ConversationSummary(
                            user_id=job.user_id,
                            conversation_id=job.conversation_id,
                            start_message_id=job.start_message_id,
                            end_message_id=job.end_message_id,
                            version=version,
                            status="failed",
                            content="",
                            error_message=job.last_error,
                        )
                    )
                else:
                    job.status = "pending"
                    job.next_retry_at = datetime.now(timezone.utc) + timedelta(
                        seconds=min(300, 2 ** min(job.attempts, 8))
                    )
        log_background_job("compression", "failed" if job.attempts >= self.max_attempts else "retry")
