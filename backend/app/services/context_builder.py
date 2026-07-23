from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage
from app.services.mcp_manager import McpManager
from app.services.memory_service import MemoryService
from app.services.skill_loader import SkillLoader


BASE_SYSTEM_PROMPT = """You are a helpful web-based assistant.
Use relevant long-term memories only when they help answer the current message.
Use available tools when they provide information or actions needed for an accurate answer.
Never claim a tool succeeded unless its result says it succeeded."""


class ContextBuilder:
    def __init__(
        self,
        skill_loader: SkillLoader,
        memory_service: MemoryService,
        mcp_manager: McpManager,
        recent_message_limit: int,
        max_context_characters: int,
    ) -> None:
        self.skill_loader = skill_loader
        self.memory_service = memory_service
        self.mcp_manager = mcp_manager
        self.recent_message_limit = recent_message_limit
        self.max_context_characters = max_context_characters

    async def build(
        self,
        session: AsyncSession,
        current_user_message: ChatMessage,
        triggered_skill: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
        """Build chat context. Returns (messages, tools, stripped_content).

        stripped_content is the user message with /skill-name prefix removed, if any.
        """
        stripped = current_user_message.content
        memories = await self.memory_service.search(stripped, current_user_message.conversation_id)
        prompt_sections = [BASE_SYSTEM_PROMPT]

        if triggered_skill:
            skill_section = self.skill_loader.prompt_section(triggered_skill)
            if skill_section:
                prompt_sections.append(skill_section)

        if memories:
            formatted = "\n".join(f"- {memory['content']}" for memory in memories)
            prompt_sections.append(f"## Relevant memories\n{formatted}")

        tools = self.mcp_manager.openai_tools()
        if tools:
            descriptions = "\n".join(
                f"- {tool['function']['name']}: {tool['function']['description']}"
                for tool in tools
            )
            prompt_sections.append(f"## Available MCP tools\n{descriptions}")

        result = await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.id <= current_user_message.id,
                ChatMessage.conversation_id == current_user_message.conversation_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(self.recent_message_limit)
        )
        recent = list(reversed(result.scalars().all()))
        messages = [{"role": "system", "content": "\n\n".join(prompt_sections)}]
        available = self.max_context_characters - len(messages[0]["content"])
        selected: list[dict[str, str]] = []
        for message in reversed(recent):
            content = message.content
            if len(content) > available and selected:
                break
            content = content[-max(available, 0) :] if not selected else content
            # For the current user message, use the stripped version in LLM context
            if message.id == current_user_message.id:
                content = stripped
            selected.append({"role": message.role, "content": content})
            available -= len(content)
            if available <= 0:
                break
        messages.extend(reversed(selected))
        return messages, tools, stripped
