import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.services.context_builder import ContextBuilder
from app.services.llm_client import LlmClient, LlmTurn
from app.services.mcp_manager import McpManager
from app.services.memory_service import MemoryService


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
    ) -> None:
        self.session_factory = session_factory
        self.llm_client = llm_client
        self.context_builder = context_builder
        self.mcp_manager = mcp_manager
        self.memory_service = memory_service
        self.max_tool_rounds = max_tool_rounds

    async def send(self, content: str, conversation_id: int | None = None) -> ChatMessage:
        user_message, messages, tools = await self._persist_and_build(content, conversation_id)
        turn = await self._run_tool_loop(messages, tools)
        assistant = await self._save_assistant(turn.content, "complete", conversation_id)
        self._schedule_memory(user_message, assistant, conversation_id)
        return assistant

    async def stream(self, content: str, conversation_id: int | None = None) -> AsyncIterator[dict[str, Any]]:
        user_message, messages, tools = await self._persist_and_build(content, conversation_id)
        accumulated = ""
        try:
            for round_index in range(self.max_tool_rounds):
                turn: LlmTurn | None = None
                async for event in self.llm_client.stream(messages, tools):
                    if event["type"] == "token":
                        accumulated += event["content"]
                        yield event
                    else:
                        turn = event["turn"]
                if turn is None:
                    raise RuntimeError("LLM stream ended without a final turn")
                if not turn.tool_calls:
                    assistant = await self._save_assistant(accumulated, "complete", conversation_id)
                    self._schedule_memory(user_message, assistant, conversation_id)
                    yield {"type": "done", "message": self.serialize_message(assistant)}
                    return

                messages.append(self._assistant_tool_message(turn))
                results = await asyncio.gather(
                    *(self._execute_tool_call(call) for call in turn.tool_calls)
                )
                messages.extend(results)
            raise RuntimeError("Maximum tool-call rounds exceeded")
        except asyncio.CancelledError:
            if accumulated:
                await self._save_assistant(accumulated, "interrupted", conversation_id)
            raise
        except Exception as exc:
            if accumulated:
                await self._save_assistant(accumulated, "interrupted", conversation_id)
            yield {"type": "error", "message": str(exc) or exc.__class__.__name__}

    async def _run_tool_loop(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LlmTurn:
        for _ in range(self.max_tool_rounds):
            turn = await self.llm_client.complete(messages, tools)
            if not turn.tool_calls:
                return turn
            messages.append(self._assistant_tool_message(turn))
            results = await asyncio.gather(
                *(self._execute_tool_call(call) for call in turn.tool_calls)
            )
            messages.extend(results)
        raise RuntimeError("Maximum tool-call rounds exceeded")

    async def _persist_and_build(
        self, content: str, conversation_id: int | None = None
    ) -> tuple[ChatMessage, list[dict[str, Any]], list[dict[str, Any]]]:
        normalized = content.strip()
        if not normalized:
            raise ValueError("Message must not be empty")
        triggered_skill: str | None = None
        if normalized.startswith("/"):
            parts = normalized.split(maxsplit=1)
            triggered_skill = parts[0][1:]  # Strip leading /
        async with self.session_factory() as session:
            user_message = ChatMessage(role="user", content=normalized, conversation_id=conversation_id)
            session.add(user_message)
            await session.commit()
            await session.refresh(user_message)
            if conversation_id is not None:
                # Auto-title: if this is the first message, use it as conversation title
                msg_count = (await session.execute(
                    select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                )).scalars().all()
                if len(msg_count) == 1:  # Only this message exists
                    title = normalized[:40] + ("…" if len(normalized) > 40 else "")
                    await session.execute(
                        update(Conversation)
                        .where(Conversation.id == conversation_id)
                        .values(title=title, updated_at=datetime.now(timezone.utc))
                    )
                else:
                    await session.execute(
                        update(Conversation)
                        .where(Conversation.id == conversation_id)
                        .values(updated_at=datetime.now(timezone.utc))
                    )
                await session.commit()
            messages, tools, stripped = await self.context_builder.build(
                session, user_message, triggered_skill
            )
        return user_message, messages, tools

    async def _save_assistant(self, content: str, status: str, conversation_id: int | None = None) -> ChatMessage:
        async with self.session_factory() as session:
            message = ChatMessage(role="assistant", content=content, status=status, conversation_id=conversation_id)
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def _execute_tool_call(self, call: dict[str, Any]) -> dict[str, Any]:
        function = call.get("function", {})
        try:
            arguments = json.loads(function.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            result: dict[str, Any] = {"ok": False, "error": str(exc)}
        else:
            result = await self.mcp_manager.execute_tool(function.get("name", ""), arguments)
        return {
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "content": json.dumps(result, ensure_ascii=False),
        }

    @staticmethod
    def _assistant_tool_message(turn: LlmTurn) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": turn.content or None,
            "tool_calls": turn.tool_calls,
        }

    def _schedule_memory(self, user: ChatMessage, assistant: ChatMessage, conversation_id: int | None = None) -> None:
        task = asyncio.create_task(
            self.memory_service.extract_and_store(
                user.content,
                assistant.content,
                [user.id, assistant.id],
                self.llm_client.extract_facts,
                conversation_id,
            )
        )
        task.add_done_callback(self._log_memory_error)

    @staticmethod
    def _log_memory_error(task: asyncio.Task[list]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("Asynchronous memory extraction failed")

    @staticmethod
    def serialize_message(message: ChatMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "status": message.status,
            "created_at": message.created_at.isoformat(),
        }
