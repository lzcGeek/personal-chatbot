import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI


@dataclass
class ToolCallAccumulator:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""

    def as_message_tool_call(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments or "{}"},
        }


@dataclass
class LlmTurn:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> LlmTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = await self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        return LlmTurn(
            content=message.content or "",
            tool_calls=[tool.model_dump(exclude_none=True) for tool in message.tool_calls or []],
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        stream = await self.client.chat.completions.create(**kwargs)
        tool_calls: dict[int, ToolCallAccumulator] = {}
        content_parts: list[str] = []
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                yield {"type": "token", "content": delta.content}
            for tool_delta in delta.tool_calls or []:
                accumulator = tool_calls.setdefault(
                    tool_delta.index, ToolCallAccumulator(index=tool_delta.index)
                )
                if tool_delta.id:
                    accumulator.id += tool_delta.id
                if tool_delta.function:
                    if tool_delta.function.name:
                        accumulator.name += tool_delta.function.name
                    if tool_delta.function.arguments:
                        accumulator.arguments += tool_delta.function.arguments
        yield {
            "type": "turn",
            "turn": LlmTurn(
                content="".join(content_parts),
                tool_calls=[
                    tool_calls[index].as_message_tool_call() for index in sorted(tool_calls)
                ],
            ),
        }

    async def extract_facts(self, user_content: str, assistant_content: str) -> list[str]:
        response = await self.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract durable user facts, preferences, goals, or decisions from the "
                        "exchange. Return only a JSON array of short standalone strings. "
                        "Return [] when nothing is worth remembering."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User message:\n{user_content}\n\n"
                        f"Assistant response:\n{assistant_content}"
                    ),
                },
            ],
            temperature=0,
        )
        try:
            value = json.loads(response.content)
        except json.JSONDecodeError:
            return []
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
