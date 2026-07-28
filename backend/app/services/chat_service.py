import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.chat_message import ChatMessage
from app.models.character import Character
from app.models.conversation import Conversation
from app.models.conversation_member import ConversationMember
from app.models.speaker_plan import SpeakerPlan
from app.services.chat_errors import ChatFailure, classify_chat_failure
from app.services.context_builder import ContextBuilder
from app.services.compression_service import CompressionService
from app.services.llm_client import LlmClient, LlmTurn
from app.services.mcp_manager import McpManager
from app.services.memory_service import MemoryService
from app.services.npc_orchestrator import NpcOrchestrator
from app.services.observability import (
    log_chat_outcome,
    log_routing,
    log_speaker_generation,
    record_metric,
    reset_request_metrics,
)


logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_client: LlmClient,
        context_builder: ContextBuilder,
        mcp_manager: McpManager,
        memory_service: MemoryService,
        max_tool_rounds: int,
        compression_service: CompressionService | None = None,
        npc_orchestrator: NpcOrchestrator | None = None,
        requests_per_minute: int = 30,
        server_max_speakers: int = 4,
        server_max_group_generations: int = 6,
        single_npc_enabled: bool = True,
        group_npc_enabled: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.llm_client = llm_client
        self.context_builder = context_builder
        self.mcp_manager = mcp_manager
        self.memory_service = memory_service
        self.max_tool_rounds = max_tool_rounds
        self.compression_service = compression_service
        self.npc_orchestrator = npc_orchestrator or NpcOrchestrator(llm_client)
        self.requests_per_minute = requests_per_minute
        self.server_max_speakers = server_max_speakers
        self.server_max_group_generations = server_max_group_generations
        self.single_npc_enabled = single_npc_enabled
        self.group_npc_enabled = group_npc_enabled
        self._request_times: dict[uuid.UUID, deque[float]] = defaultdict(deque)
        self._request_locks: dict[tuple[uuid.UUID, uuid.UUID], asyncio.Lock] = {}

    async def send(
        self,
        content: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        allow_network: bool = False,
        client_request_id: uuid.UUID | None = None,
        target_character_id: uuid.UUID | None = None,
        max_speakers: int | None = None,
    ) -> ChatMessage:
        request_id = client_request_id or uuid.uuid4()
        self._check_rate_limit(user_id)
        reset_request_metrics()
        started = time.monotonic()
        async with self._lock_for(user_id, request_id):
            try:
                if self.session_factory is not None and await self._conversation_mode(user_id, conversation_id) == "group":
                    return await self._send_group(
                        content,
                        user_id,
                        conversation_id,
                        allow_network,
                        client_request_id,
                        request_id,
                        target_character_id,
                        max_speakers,
                    )
                build_result = await self._persist_and_build(
                        content,
                        user_id,
                        conversation_id,
                        allow_network,
                        client_request_id,
                    )
                if len(build_result) == 6:
                    user_message, messages, tools, citations, degradations, replay = build_result
                    speaker, effective_network = None, allow_network
                else:
                    (
                        user_message, messages, tools, citations, degradations,
                        replay, speaker, effective_network,
                    ) = build_result
                if replay is not None:
                    return replay
                turn = await self._execute_speaker(
                    messages, tools, user_id, effective_network, degradations
                )
                assistant = await self._save_response(
                    turn.content, "complete", conversation_id, citations, speaker
                )
                self._schedule_memory(user_message, assistant, user_id, conversation_id)
                log_chat_outcome(
                    request_id=str(request_id),
                    outcome="degraded" if degradations else "complete",
                    duration_ms=self._elapsed_ms(started),
                    degradations=degradations,
                )
                return assistant
            except (ValueError, ChatFailure):
                raise
            except Exception as exc:
                failure = classify_chat_failure(exc)
                log_chat_outcome(
                    request_id=str(request_id),
                    outcome="error",
                    duration_ms=self._elapsed_ms(started),
                    error_code=failure.code,
                )
                raise failure from exc

    async def stream(
        self,
        content: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        allow_network: bool = False,
        client_request_id: uuid.UUID | None = None,
        target_character_id: uuid.UUID | None = None,
        max_speakers: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        request_id = client_request_id or uuid.uuid4()
        self._check_rate_limit(user_id)
        reset_request_metrics()
        async with self._lock_for(user_id, request_id):
            if self.session_factory is not None and await self._conversation_mode(user_id, conversation_id) == "group":
                async for event in self._stream_group(
                    content,
                    user_id,
                    conversation_id,
                    allow_network,
                    client_request_id,
                    request_id,
                    target_character_id,
                    max_speakers,
                ):
                    yield event
                return
            async for event in self._stream_locked(
                content,
                user_id,
                conversation_id,
                allow_network,
                client_request_id,
                request_id,
            ):
                yield event

    async def _conversation_mode(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str:
        async with self.session_factory() as session:
            mode = await session.scalar(
                select(Conversation.mode).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
        if mode is None:
            raise ValueError("Conversation not found")
        if mode == "group" and not self.group_npc_enabled:
            raise ChatFailure("group_npc_disabled", "多角色编排尚未启用。", False)
        return mode

    async def _prepare_group_request(
        self,
        content: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        allow_network: bool,
        client_request_id: uuid.UUID | None,
        request_id: uuid.UUID,
        target_character_id: uuid.UUID | None,
        requested_max_speakers: int | None,
    ) -> tuple[ChatMessage, Conversation, SpeakerPlan, list[Character]]:
        normalized = content.strip()
        if not normalized:
            raise ValueError("Message must not be empty")
        async with self.session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            if conversation is None or conversation.mode != "group":
                raise ValueError("Group conversation not found")
            plan = await session.scalar(
                select(SpeakerPlan).where(
                    SpeakerPlan.conversation_id == conversation_id,
                    SpeakerPlan.user_id == user_id,
                    SpeakerPlan.request_id == request_id,
                )
            )
            if plan is not None:
                user_message = await session.get(ChatMessage, plan.user_message_id)
                if (
                    user_message is None
                    or user_message.content != normalized
                    or user_message.allow_network != allow_network
                ):
                    raise ChatFailure(
                        "idempotency_conflict",
                        "该重试标识已用于不同的请求。",
                        False,
                    )
                speakers = await self._load_plan_speakers(session, plan, user_id)
                return user_message, conversation, plan, speakers

            user_message = await self._existing_user_message(
                session, conversation_id, client_request_id
            )
            created = user_message is None
            if user_message is not None and (
                user_message.content != normalized or user_message.allow_network != allow_network
            ):
                raise ChatFailure(
                    "idempotency_conflict", "该重试标识已用于不同的请求。", False
                )
            if user_message is None:
                user_message = ChatMessage(
                    role="user",
                    content=normalized,
                    conversation_id=conversation_id,
                    client_request_id=client_request_id,
                    allow_network=allow_network,
                )
                session.add(user_message)
                try:
                    await session.commit()
                    await session.refresh(user_message)
                except IntegrityError:
                    await session.rollback()
                    user_message = await self._existing_user_message(
                        session, conversation_id, client_request_id
                    )
                    if user_message is None:
                        raise
                    created = False

            member_rows = await session.execute(
                select(Character)
                .join(ConversationMember, ConversationMember.character_id == Character.id)
                .where(
                    ConversationMember.conversation_id == conversation_id,
                    ConversationMember.user_id == user_id,
                    ConversationMember.enabled.is_(True),
                    Character.user_id == user_id,
                    Character.archived.is_(False),
                    Character.deleted_at.is_(None),
                )
                .order_by(ConversationMember.position, ConversationMember.id)
            )
            members = list(member_rows.scalars())
            previous_character_id = await session.scalar(
                select(ChatMessage.character_id)
                .where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.role == "assistant",
                    ChatMessage.character_id.is_not(None),
                    ChatMessage.id < user_message.id,
                )
                .order_by(ChatMessage.id.desc())
                .limit(1)
            )
            limit = min(
                requested_max_speakers or conversation.max_speakers_per_turn,
                conversation.max_speakers_per_turn,
                conversation.max_group_generations,
                self.server_max_speakers,
                self.server_max_group_generations,
            )
            decision = await self.npc_orchestrator.select(
                conversation.routing_strategy,
                normalized,
                members,
                max_speakers=limit,
                target_character_id=target_character_id,
                previous_character_id=previous_character_id,
            )
            plan = SpeakerPlan(
                user_id=user_id,
                conversation_id=conversation_id,
                user_message_id=user_message.id,
                request_id=request_id,
                strategy=conversation.routing_strategy,
                speaker_ids=[str(value) for value in decision.speaker_ids],
                reason_code=decision.reason_code,
                metadata_json={"speaker_limit": limit},
            )
            session.add(plan)
            if created:
                conversation.title = normalized[:40] + ("…" if len(normalized) > 40 else "")
            try:
                await session.commit()
                await session.refresh(plan)
            except IntegrityError:
                await session.rollback()
                plan = await session.scalar(
                    select(SpeakerPlan).where(
                        SpeakerPlan.conversation_id == conversation_id,
                        SpeakerPlan.user_id == user_id,
                        SpeakerPlan.request_id == request_id,
                    )
                )
                if plan is None:
                    raise
            log_routing(
                str(plan.id), plan.strategy, len(plan.speaker_ids), plan.reason_code
            )
            speakers = await self._load_plan_speakers(session, plan, user_id)
            return user_message, conversation, plan, speakers

    @staticmethod
    async def _load_plan_speakers(
        session: AsyncSession, plan: SpeakerPlan, user_id: uuid.UUID
    ) -> list[Character]:
        ids = [uuid.UUID(value) for value in plan.speaker_ids]
        rows = await session.execute(
            select(Character).where(
                Character.id.in_(ids),
                Character.user_id == user_id,
                Character.deleted_at.is_(None),
            )
        )
        by_id = {item.id: item for item in rows.scalars()}
        if any(character_id not in by_id for character_id in ids):
            raise ValueError("Persisted speaker plan contains an unavailable character")
        return [by_id[character_id] for character_id in ids]

    async def _group_responses(self, plan_id: uuid.UUID) -> list[ChatMessage]:
        async with self.session_factory() as session:
            rows = await session.execute(
                select(ChatMessage)
                .where(ChatMessage.speaker_plan_id == plan_id)
                .order_by(ChatMessage.speaker_plan_index)
            )
            return list(rows.scalars())

    async def _build_group_context(
        self,
        user_message: ChatMessage,
        conversation: Conversation,
        user_id: uuid.UUID,
        speaker: Character,
        allow_network: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], bool]:
        effective_network = allow_network and bool(speaker.permissions.get("tools")) and bool(
            speaker.permissions.get("network")
        )
        triggered_skill = None
        if user_message.content.startswith("/"):
            triggered_skill = user_message.content.split(maxsplit=1)[0][1:]
        async with self.session_factory() as session:
            history_through_id = await session.scalar(
                select(func.max(ChatMessage.id)).where(
                    ChatMessage.conversation_id == conversation.id
                )
            )
            messages, tools, _, citations, degradations = await self.context_builder.build(
                session,
                user_message,
                user_id,
                triggered_skill,
                allow_network=effective_network,
                retrieval_mode=conversation.retrieval_mode,
                character=speaker,
                history_through_id=history_through_id,
            )
        return messages, tools, citations, degradations, effective_network

    async def _save_group_response(
        self,
        content: str,
        conversation_id: uuid.UUID,
        citations: list[dict[str, Any]],
        speaker: Character,
        plan_id: uuid.UUID,
        plan_index: int,
    ) -> ChatMessage:
        async with self.session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(ChatMessage).where(
                        ChatMessage.speaker_plan_id == plan_id,
                        ChatMessage.speaker_plan_index == plan_index,
                    )
                )
                if existing is not None:
                    return existing
                plan = await session.get(SpeakerPlan, plan_id, with_for_update=True)
                if plan is None or plan.current_index != plan_index:
                    raise RuntimeError("Speaker plan progress conflict")
                message = ChatMessage(
                    role="assistant",
                    content=content,
                    status="complete",
                    citations=citations,
                    conversation_id=conversation_id,
                    character_id=speaker.id,
                    speaker_name=speaker.name,
                    speaker_plan_id=plan_id,
                    speaker_plan_index=plan_index,
                )
                session.add(message)
                plan.current_index = plan_index + 1
                plan.status = "running"
            await session.refresh(message)
            return message

    async def _update_group_plan(self, plan_id: uuid.UUID, **values: Any) -> None:
        async with self.session_factory() as session:
            await session.execute(update(SpeakerPlan).where(SpeakerPlan.id == plan_id).values(**values))
            await session.commit()

    async def _send_group(
        self,
        content: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        allow_network: bool,
        client_request_id: uuid.UUID | None,
        request_id: uuid.UUID,
        target_character_id: uuid.UUID | None,
        max_speakers: int | None,
    ) -> ChatMessage:
        started = time.monotonic()
        user_message, conversation, plan, speakers = await self._prepare_group_request(
            content, user_id, conversation_id, allow_network, client_request_id,
            request_id, target_character_id, max_speakers,
        )
        responses = await self._group_responses(plan.id)
        if plan.status == "complete" and responses:
            return responses[-1]
        try:
            for index in range(plan.current_index, len(speakers)):
                speaker = speakers[index]
                speaker_started = time.monotonic()
                messages, tools, citations, degradations, effective_network = (
                    await self._build_group_context(
                        user_message, conversation, user_id, speaker, allow_network
                    )
                )
                turn = await self._execute_speaker(
                    messages, tools, user_id, effective_network, degradations
                )
                response = await self._save_group_response(
                    turn.content, conversation_id, citations, speaker, plan.id, index
                )
                responses.append(response)
                log_speaker_generation(
                    str(plan.id), index, "complete", self._elapsed_ms(speaker_started)
                )
                self._schedule_memory(user_message, response, user_id, conversation_id)
            await self._update_group_plan(
                plan.id, status="complete", duration_ms=self._elapsed_ms(started), error_code=None
            )
            if not responses:
                raise RuntimeError("Speaker plan completed without a response")
            return responses[-1]
        except Exception as exc:
            failure = classify_chat_failure(exc)
            await self._update_group_plan(
                plan.id,
                status="failed",
                duration_ms=self._elapsed_ms(started),
                error_code=failure.code,
            )
            raise

    async def _stream_group(
        self,
        content: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        allow_network: bool,
        client_request_id: uuid.UUID | None,
        request_id: uuid.UUID,
        target_character_id: uuid.UUID | None,
        max_speakers: int | None,
    ) -> AsyncIterator[dict[str, Any]]:
        started = time.monotonic()
        responses: list[ChatMessage] = []
        try:
            user_message, conversation, plan, speakers = await self._prepare_group_request(
                content, user_id, conversation_id, allow_network, client_request_id,
                request_id, target_character_id, max_speakers,
            )
            responses = await self._group_responses(plan.id)
            yield {
                "type": "routing",
                "plan_id": str(plan.id),
                "strategy": plan.strategy,
                "speaker_ids": plan.speaker_ids,
                "reason_code": plan.reason_code,
                "resumed_from": plan.current_index,
            }
            if plan.status != "complete":
                for index in range(plan.current_index, len(speakers)):
                    speaker = speakers[index]
                    speaker_started = time.monotonic()
                    yield {
                        "type": "speaker_start",
                        "character_id": str(speaker.id),
                        "speaker_name": speaker.name,
                        "plan_index": index,
                    }
                    messages, tools, citations, degradations, effective_network = (
                        await self._build_group_context(
                            user_message, conversation, user_id, speaker, allow_network
                        )
                    )
                    turn = await self._execute_speaker(
                        messages, tools, user_id, effective_network, degradations
                    )
                    yield {
                        "type": "token",
                        "content": turn.content,
                        "character_id": str(speaker.id),
                        "speaker_name": speaker.name,
                        "plan_index": index,
                    }
                    response = await self._save_group_response(
                        turn.content, conversation_id, citations, speaker, plan.id, index
                    )
                    responses.append(response)
                    log_speaker_generation(
                        str(plan.id), index, "complete", self._elapsed_ms(speaker_started)
                    )
                    self._schedule_memory(user_message, response, user_id, conversation_id)
                    yield {
                        "type": "speaker_done",
                        "character_id": str(speaker.id),
                        "speaker_name": speaker.name,
                        "plan_index": index,
                        "message": self.serialize_message(response),
                    }
                await self._update_group_plan(
                    plan.id, status="complete", duration_ms=self._elapsed_ms(started), error_code=None
                )
            if not responses:
                raise RuntimeError("Speaker plan completed without a response")
            yield {
                "type": "done",
                "message": self.serialize_message(responses[-1]),
                "messages": [self.serialize_message(item) for item in responses],
                "degraded": False,
                "degradations": [],
                "request_id": str(request_id),
                "plan_id": str(plan.id),
            }
        except Exception as exc:
            failure = classify_chat_failure(exc)
            plan_id = locals().get("plan").id if locals().get("plan") is not None else None
            if plan_id is not None:
                await self._update_group_plan(
                    plan_id,
                    status="failed",
                    duration_ms=self._elapsed_ms(started),
                    error_code=failure.code,
                )
            yield {
                "type": "error",
                "code": failure.code,
                "message": failure.user_message,
                "recoverable": failure.recoverable,
                "request_id": str(request_id),
                "partial_saved": bool(responses),
                "completed_messages": [self.serialize_message(item) for item in responses],
            }

    async def _stream_locked(
        self,
        content: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        allow_network: bool,
        client_request_id: uuid.UUID | None,
        request_id: uuid.UUID,
    ) -> AsyncIterator[dict[str, Any]]:
        started = time.monotonic()
        accumulated = ""
        citations: list[dict[str, Any]] = []
        degradations: list[str] = []
        speaker: Character | None = None
        try:
            build_result = await self._persist_and_build(
                    content,
                    user_id,
                    conversation_id,
                    allow_network,
                    client_request_id,
                )
            if len(build_result) == 6:
                user_message, messages, tools, citations, initial_degradations, replay = build_result
                speaker, effective_network = None, allow_network
            else:
                (
                    user_message, messages, tools, citations, initial_degradations,
                    replay, speaker, effective_network,
                ) = build_result
            degradations.extend(initial_degradations)
            if replay is not None:
                yield {
                    "type": "done",
                    "message": self.serialize_message(replay),
                    "degraded": False,
                    "degradations": [],
                    "request_id": str(request_id),
                }
                return

            if speaker is not None:
                yield {
                    "type": "speaker_start",
                    "character_id": str(speaker.id),
                    "speaker_name": speaker.name,
                }

            for _ in range(self.max_tool_rounds):
                turn: LlmTurn | None = None
                async for event in self.llm_client.stream(messages, tools):
                    if event["type"] == "token":
                        accumulated += event["content"]
                        token_event = dict(event)
                        if speaker is not None:
                            token_event.update(
                                character_id=str(speaker.id), speaker_name=speaker.name
                            )
                        yield token_event
                    else:
                        turn = event["turn"]
                if turn is None:
                    raise RuntimeError("LLM stream ended without a final turn")
                if not turn.tool_calls:
                    assistant = await self._save_response(
                        accumulated, "complete", conversation_id, citations, speaker
                    )
                    self._schedule_memory(user_message, assistant, user_id, conversation_id)
                    outcome = "degraded" if degradations else "complete"
                    log_chat_outcome(
                        request_id=str(request_id),
                        outcome=outcome,
                        duration_ms=self._elapsed_ms(started),
                        degradations=degradations,
                    )
                    if speaker is not None:
                        yield {
                            "type": "speaker_done",
                            "character_id": str(speaker.id),
                            "speaker_name": speaker.name,
                            "message_id": assistant.id,
                        }
                    yield {
                        "type": "done",
                        "message": self.serialize_message(assistant),
                        "degraded": bool(degradations),
                        "degradations": list(dict.fromkeys(degradations)),
                        "request_id": str(request_id),
                    }
                    return

                messages.append(self._assistant_tool_message(turn))
                results = await asyncio.gather(
                    *(
                        self._execute_tool_call(
                            call,
                            user_id,
                            effective_network,
                            degradations,
                            self._allowed_tool_names(tools),
                        )
                        for call in turn.tool_calls
                    )
                )
                messages.extend(results)

            degradations.append("tool_round_limit_reached")
            record_metric("chat.fallback.tool_round_limit")
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Tool use has ended. Produce the best final answer from the results "
                        "already available and disclose any missing or failed online retrieval."
                    ),
                }
            )
            final_turn = await self.llm_client.complete(messages, tools=None)
            if final_turn.content:
                accumulated += final_turn.content
                token_event = {"type": "token", "content": final_turn.content}
                if speaker is not None:
                    token_event.update(
                        character_id=str(speaker.id), speaker_name=speaker.name
                    )
                yield token_event
            assistant = await self._save_response(
                accumulated, "complete", conversation_id, citations, speaker
            )
            self._schedule_memory(user_message, assistant, user_id, conversation_id)
            log_chat_outcome(
                request_id=str(request_id),
                outcome="degraded",
                duration_ms=self._elapsed_ms(started),
                degradations=degradations,
            )
            if speaker is not None:
                yield {
                    "type": "speaker_done",
                    "character_id": str(speaker.id),
                    "speaker_name": speaker.name,
                    "message_id": assistant.id,
                }
            yield {
                "type": "done",
                "message": self.serialize_message(assistant),
                "degraded": True,
                "degradations": list(dict.fromkeys(degradations)),
                "request_id": str(request_id),
            }
        except asyncio.CancelledError:
            if accumulated:
                await self._save_response(
                    accumulated, "interrupted", conversation_id, citations, speaker
                )
            raise
        except Exception as exc:
            partial_saved = False
            if accumulated:
                await self._save_response(
                    accumulated, "interrupted", conversation_id, citations, speaker
                )
                partial_saved = True
            failure = classify_chat_failure(exc)
            log_chat_outcome(
                request_id=str(request_id),
                outcome="error",
                duration_ms=self._elapsed_ms(started),
                error_code=failure.code,
                degradations=degradations,
            )
            yield {
                "type": "error",
                "code": failure.code,
                "message": failure.user_message,
                "recoverable": failure.recoverable,
                "request_id": str(request_id),
                "partial_saved": partial_saved,
                "character_id": str(speaker.id) if speaker is not None else None,
                "speaker_name": speaker.name if speaker is not None else None,
            }

    async def _execute_speaker(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        user_id: uuid.UUID,
        allow_network: bool,
        degradations: list[str],
    ) -> LlmTurn:
        allowed_tool_names = self._allowed_tool_names(tools)
        for _ in range(self.max_tool_rounds):
            turn = await self.llm_client.complete(messages, tools)
            if not turn.tool_calls:
                return turn
            messages.append(self._assistant_tool_message(turn))
            results = await asyncio.gather(
                *(
                    self._execute_tool_call(
                        call, user_id, allow_network, degradations, allowed_tool_names
                    )
                    for call in turn.tool_calls
                )
            )
            messages.extend(results)
        degradations.append("tool_round_limit_reached")
        messages.append(
            {
                "role": "system",
                "content": (
                    "Tool use has ended. Produce the best final answer from existing results "
                    "and disclose failed online retrieval."
                ),
            }
        )
        return await self.llm_client.complete(messages, tools=None)

    async def _run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        user_id: uuid.UUID,
        allow_network: bool,
        degradations: list[str],
    ) -> LlmTurn:
        """Compatibility alias for callers predating the reusable speaker executor."""
        return await self._execute_speaker(
            messages, tools, user_id, allow_network, degradations
        )

    async def _persist_and_build(
        self,
        content: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        allow_network: bool,
        client_request_id: uuid.UUID | None,
    ) -> tuple[
        ChatMessage,
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[str],
        ChatMessage | None,
        Character | None,
        bool,
    ]:
        normalized = content.strip()
        if not normalized:
            raise ValueError("Message must not be empty")
        triggered_skill: str | None = None
        if normalized.startswith("/"):
            parts = normalized.split(maxsplit=1)
            triggered_skill = parts[0][1:]

        async with self.session_factory() as session:
            conversation = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if conversation is None:
                raise ValueError("Conversation not found")

            speaker: Character | None = None
            if conversation.mode == "single_character":
                if not self.single_npc_enabled:
                    raise ChatFailure("single_npc_disabled", "单角色 NPC 尚未启用。", False)
                speaker_result = await session.execute(
                    select(Character)
                    .join(
                        ConversationMember,
                        ConversationMember.character_id == Character.id,
                    )
                    .where(
                        ConversationMember.conversation_id == conversation.id,
                        ConversationMember.user_id == user_id,
                        ConversationMember.enabled.is_(True),
                        Character.user_id == user_id,
                        Character.archived.is_(False),
                        Character.deleted_at.is_(None),
                    )
                    .order_by(ConversationMember.position)
                    .limit(2)
                )
                speakers = list(speaker_result.scalars())
                if len(speakers) != 1:
                    raise ValueError(
                        "Single-character conversation requires one active character"
                    )
                speaker = speakers[0]
            effective_network = allow_network and (
                speaker is None
                or (
                    bool(speaker.permissions.get("tools"))
                    and bool(speaker.permissions.get("network"))
                )
            )

            user_message = await self._existing_user_message(
                session, conversation_id, client_request_id
            )
            created = user_message is None
            if user_message is not None:
                if (
                    user_message.content != normalized
                    or user_message.allow_network != allow_network
                ):
                    raise ChatFailure(
                        "idempotency_conflict",
                        "该重试标识已用于不同的请求。",
                        False,
                    )
            else:
                user_message = ChatMessage(
                    role="user",
                    content=normalized,
                    conversation_id=conversation_id,
                    client_request_id=client_request_id,
                    allow_network=allow_network,
                )
                session.add(user_message)
                try:
                    await session.commit()
                    await session.refresh(user_message)
                except IntegrityError:
                    await session.rollback()
                    user_message = await self._existing_user_message(
                        session, conversation_id, client_request_id
                    )
                    if user_message is None:
                        raise
                    created = False

            if not created:
                replay = await session.scalar(
                    select(ChatMessage)
                    .where(
                        ChatMessage.conversation_id == conversation_id,
                        ChatMessage.role == "assistant",
                        ChatMessage.status == "complete",
                        ChatMessage.id > user_message.id,
                    )
                    .order_by(ChatMessage.id)
                    .limit(1)
                )
                if replay is not None:
                    return (
                        user_message,
                        [],
                        [],
                        [],
                        [],
                        replay,
                        speaker,
                        effective_network,
                    )

            if created:
                message_count = await session.scalar(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.conversation_id == conversation_id
                    )
                )
                values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
                if message_count == 1:
                    values["title"] = normalized[:40] + (
                        "…" if len(normalized) > 40 else ""
                    )
                await session.execute(
                    update(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .values(**values)
                )
                await session.commit()

            messages, tools, _, citations, degradations = (
                await self.context_builder.build(
                    session,
                    user_message,
                    user_id,
                    triggered_skill,
                    allow_network=effective_network,
                    retrieval_mode=conversation.retrieval_mode,
                    character=speaker,
                )
            )
        return (
            user_message,
            messages,
            tools,
            citations,
            degradations,
            None,
            speaker,
            effective_network,
        )

    @staticmethod
    async def _existing_user_message(
        session: AsyncSession,
        conversation_id: uuid.UUID,
        client_request_id: uuid.UUID | None,
    ) -> ChatMessage | None:
        if client_request_id is None:
            return None
        return await session.scalar(
            select(ChatMessage).where(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.client_request_id == client_request_id,
                ChatMessage.role == "user",
            )
        )

    async def _save_response(
        self,
        content: str,
        status: str,
        conversation_id: uuid.UUID,
        citations: list[dict[str, Any]],
        speaker: Character | None,
    ) -> ChatMessage:
        if speaker is None:
            return await self._save_assistant(
                content, status, conversation_id, citations
            )
        return await self._save_assistant(
            content, status, conversation_id, citations, speaker
        )

    async def _save_assistant(
        self,
        content: str,
        status: str,
        conversation_id: uuid.UUID,
        citations: list[dict[str, Any]],
        speaker: Character | None = None,
    ) -> ChatMessage:
        async with self.session_factory() as session:
            message = ChatMessage(
                role="assistant",
                content=content,
                status=status,
                citations=citations,
                conversation_id=conversation_id,
                character_id=speaker.id if speaker is not None else None,
                speaker_name=speaker.name if speaker is not None else None,
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def _execute_tool_call(
        self,
        call: dict[str, Any],
        user_id: uuid.UUID,
        allow_network: bool,
        degradations: list[str],
        allowed_tool_names: set[str] | None = None,
    ) -> dict[str, Any]:
        function = call.get("function", {})
        exposed_name = function.get("name", "")
        if allowed_tool_names is not None and exposed_name not in allowed_tool_names:
            degradations.append("mcp_tool_not_authorized")
            return {
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(
                    {
                        "ok": False,
                        "code": "mcp_tool_not_authorized",
                        "error": "Tool is not authorized",
                    }
                ),
            }
        try:
            arguments = json.loads(function.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError):
            result: dict[str, Any] = {
                "ok": False,
                "code": "mcp_invalid_arguments",
                "error": "The tool arguments were invalid",
            }
        else:
            result = await self.mcp_manager.execute_tool(
                user_id,
                exposed_name,
                arguments,
                allow_network=allow_network,
            )
        if not result.get("ok"):
            code = str(result.get("code") or "mcp_tool_failed")
            degradation = (
                "network_tool_failed"
                if self.mcp_manager.is_network_tool(user_id, exposed_name)
                else code
            )
            degradations.append(degradation)
        return {
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "content": json.dumps(result, ensure_ascii=False),
        }

    @staticmethod
    def _allowed_tool_names(tools: list[dict[str, Any]]) -> set[str] | None:
        names: set[str] = set()
        for tool in tools:
            function = tool.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                return None
            names.add(function["name"])
        return names

    @staticmethod
    def _assistant_tool_message(turn: LlmTurn) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": turn.content or None,
            "tool_calls": turn.tool_calls,
        }

    def _schedule_memory(
        self,
        user: ChatMessage,
        assistant: ChatMessage,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        candidate_extractor = getattr(
            self.llm_client, "extract_memory_candidates", None
        )
        structured_store = getattr(
            self.memory_service, "extract_structured_and_store", None
        )
        args: list[Any] = [
            user.content,
            assistant.content,
            [user.id, assistant.id],
            (
                candidate_extractor
                if callable(candidate_extractor) and callable(structured_store)
                else self.llm_client.extract_facts
            ),
            user_id,
            conversation_id,
        ]
        character_id = getattr(assistant, "character_id", None)
        if character_id is not None:
            args.extend(["character_private", character_id])
        store = (
            structured_store
            if callable(candidate_extractor) and callable(structured_store)
            else self.memory_service.extract_and_store
        )
        task = asyncio.create_task(store(*args))
        task.add_done_callback(self._log_memory_error)
        if self.compression_service is not None:
            compression = asyncio.create_task(
                self.compression_service.enqueue_if_needed(user_id, conversation_id)
            )
            compression.add_done_callback(self._log_compression_error)

    @staticmethod
    def _log_memory_error(task: asyncio.Task[list]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("Asynchronous memory extraction failed")

    @staticmethod
    def _log_compression_error(task: asyncio.Task[bool]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("Asynchronous conversation compression scheduling failed")

    def _lock_for(self, user_id: uuid.UUID, request_id: uuid.UUID) -> asyncio.Lock:
        return self._request_locks.setdefault((user_id, request_id), asyncio.Lock())

    def _check_rate_limit(self, user_id: uuid.UUID) -> None:
        now = time.monotonic()
        timestamps = self._request_times[user_id]
        while timestamps and timestamps[0] <= now - 60:
            timestamps.popleft()
        if len(timestamps) >= self.requests_per_minute:
            raise ChatFailure("chat_rate_limit", "请求过于频繁，请稍后再试。", True)
        timestamps.append(now)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    @staticmethod
    def serialize_message(message: ChatMessage) -> dict[str, Any]:
        serialized = {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "status": message.status,
            "citations": message.citations,
            "allow_network": message.allow_network,
            "client_request_id": (
                str(message.client_request_id) if message.client_request_id else None
            ),
            "created_at": message.created_at.isoformat(),
        }
        character_id = getattr(message, "character_id", None)
        speaker_name = getattr(message, "speaker_name", None)
        if character_id is not None:
            serialized["character_id"] = str(character_id)
        if speaker_name is not None:
            serialized["speaker_name"] = speaker_name
        speaker_plan_id = getattr(message, "speaker_plan_id", None)
        speaker_plan_index = getattr(message, "speaker_plan_index", None)
        if speaker_plan_id is not None:
            serialized["speaker_plan_id"] = str(speaker_plan_id)
            serialized["speaker_plan_index"] = speaker_plan_index
        return serialized
