import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.mcp_server import McpServer


logger = logging.getLogger(__name__)


@dataclass
class ToolRequest:
    name: str
    arguments: dict[str, Any]
    future: asyncio.Future[dict[str, Any]]


@dataclass
class ServerWorker:
    task: asyncio.Task[None] | None = None
    queue: asyncio.Queue[ToolRequest] = field(default_factory=asyncio.Queue)
    attempted: asyncio.Event = field(default_factory=asyncio.Event)
    tools: list[dict[str, Any]] = field(default_factory=list)


class McpManager:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        allowed_commands: set[str],
        reconnect_seconds: float,
        tool_timeout_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.allowed_commands = allowed_commands
        self.reconnect_seconds = reconnect_seconds
        self.tool_timeout_seconds = tool_timeout_seconds
        self._workers: dict[int, ServerWorker] = {}
        self._tool_routes: dict[str, tuple[int, str]] = {}
        self._closing = False

    async def restore(self) -> None:
        async with self.session_factory() as session:
            result = await session.execute(select(McpServer).where(McpServer.enabled == True))
            servers = list(result.scalars())
        for server in servers:
            self.start(server)

    def start(self, server: McpServer) -> ServerWorker:
        existing = self._workers.get(server.id)
        if existing and existing.task is not None and not existing.task.done():
            return existing
        worker = ServerWorker()
        worker.task = asyncio.create_task(
            self._run_worker(server.id, worker), name=f"mcp-server-{server.id}"
        )
        self._workers[server.id] = worker
        return worker

    async def connect_and_wait(self, server: McpServer) -> None:
        worker = self.start(server)
        try:
            await asyncio.wait_for(worker.attempted.wait(), timeout=self.tool_timeout_seconds)
        except TimeoutError as exc:
            raise RuntimeError("MCP connection timed out") from exc
        async with self.session_factory() as session:
            current = await session.get(McpServer, server.id)
            if current is None or current.status != "connected":
                detail = current.last_error if current else "Server configuration disappeared"
                raise RuntimeError(detail or "MCP connection failed")

    async def stop(self, server_id: int) -> None:
        worker = self._workers.pop(server_id, None)
        self._remove_routes(server_id)
        if worker is None:
            return
        if worker.task is not None:
            worker.task.cancel()
            await asyncio.gather(worker.task, return_exceptions=True)

    async def close(self) -> None:
        self._closing = True
        await asyncio.gather(
            *(self.stop(server_id) for server_id in list(self._workers)),
            return_exceptions=True,
        )

    async def set_enabled(self, server_id: int, enabled: bool) -> bool:
        async with self.session_factory() as session:
            server = await session.get(McpServer, server_id)
            if server is None:
                return False
            server.enabled = enabled
            await session.commit()
        if enabled:
            self.start(server)
        else:
            await self.stop(server_id)
        return True

    async def execute_tool(
        self, exposed_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        route = self._tool_routes.get(exposed_name)
        if route is None:
            return {"ok": False, "error": f"Unknown or unavailable tool: {exposed_name}"}
        server_id, original_name = route
        worker = self._workers.get(server_id)
        if worker is None or worker.task is None or worker.task.done():
            return {"ok": False, "error": f"MCP server is disconnected: {server_id}"}
        tool = next((item for item in worker.tools if item["name"] == original_name), None)
        if tool is None:
            return {"ok": False, "error": f"Tool schema is unavailable: {exposed_name}"}
        try:
            validate(instance=arguments, schema=tool.get("inputSchema") or {"type": "object"})
        except ValidationError as exc:
            return {"ok": False, "error": f"Invalid tool arguments: {exc.message}"}

        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        await worker.queue.put(ToolRequest(original_name, arguments, future))
        try:
            return await asyncio.wait_for(future, timeout=self.tool_timeout_seconds)
        except TimeoutError:
            if not future.done():
                future.cancel()
            return {"ok": False, "error": f"Tool call timed out: {exposed_name}"}

    def openai_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for exposed_name, (server_id, original_name) in self._tool_routes.items():
            worker = self._workers.get(server_id)
            if worker is None or worker.task is None or worker.task.done():
                continue
            cached = worker.tools
            tool = next((item for item in cached if item["name"] == original_name), None)
            if tool is None:
                continue
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": exposed_name,
                        "description": tool.get("description") or "MCP tool",
                        "parameters": tool.get("inputSchema") or {
                            "type": "object",
                            "properties": {},
                        },
                    },
                }
            )
        return tools

    async def _run_worker(self, server_id: int, worker: ServerWorker) -> None:
        while not self._closing:
            try:
                server = await self._get_server(server_id)
                if server is None:
                    return
                async with self._session(server) as session:
                    await session.initialize()
                    discovered = await session.list_tools()
                    tools = [tool.model_dump(mode="json") for tool in discovered.tools]
                    worker.tools = tools
                    self._set_routes(server, tools)
                    await self._update_status(server_id, "connected", None, tools)
                    worker.attempted.set()
                    await self._serve_requests(session, worker)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._remove_routes(server_id)
                message = str(exc) or exc.__class__.__name__
                logger.warning("MCP server %s disconnected: %s", server_id, message)
                await self._update_status(server_id, "disconnected", message, [])
                worker.attempted.set()
                await asyncio.sleep(self.reconnect_seconds)

    async def _serve_requests(
        self, session: ClientSession, worker: ServerWorker
    ) -> None:
        while True:
            request = await worker.queue.get()
            try:
                result = await session.call_tool(
                    request.name,
                    request.arguments,
                    read_timeout_seconds=timedelta(seconds=self.tool_timeout_seconds),
                )
                payload = result.model_dump(mode="json")
                response = {
                    "ok": not bool(getattr(result, "isError", False)),
                    "result": payload,
                }
                if not request.future.done():
                    request.future.set_result(response)
            except Exception as exc:
                if not request.future.done():
                    request.future.set_result(
                        {"ok": False, "error": str(exc) or exc.__class__.__name__}
                    )
                raise
            finally:
                worker.queue.task_done()

    @asynccontextmanager
    async def _session(self, server: McpServer) -> AsyncIterator[ClientSession]:
        async with AsyncExitStack() as stack:
            if server.transport == "stdio":
                command = self._validate_stdio_command(server.command)
                params = StdioServerParameters(
                    command=command,
                    args=server.args or [],
                    env={**os.environ, **(server.env or {})},
                )
                read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            elif server.transport == "sse":
                read_stream, write_stream = await stack.enter_async_context(
                    sse_client(server.url, headers=server.headers or None)
                )
            elif server.transport == "http":
                streams = await stack.enter_async_context(
                    streamablehttp_client(server.url, headers=server.headers or None)
                )
                read_stream, write_stream = streams[0], streams[1]
            else:
                raise ValueError(f"Unsupported MCP transport: {server.transport}")
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            yield session

    def _validate_stdio_command(self, command: str | None) -> str:
        if not command:
            raise ValueError("stdio command is required")
        executable = Path(command).name.lower()
        for suffix in (".cmd", ".exe", ".bat"):
            if executable.endswith(suffix):
                executable = executable[: -len(suffix)]
                break
        if executable not in self.allowed_commands:
            allowed = ", ".join(sorted(self.allowed_commands))
            raise ValueError(f"stdio command '{executable}' is not allowed; allowed: {allowed}")
        return command

    def _set_routes(self, server: McpServer, tools: list[dict[str, Any]]) -> None:
        self._remove_routes(server.id)
        server_slug = self._sanitize_name(server.name)
        for tool in tools:
            exposed = f"{server_slug}__{self._sanitize_name(tool['name'])}"[:64]
            self._tool_routes[exposed] = (server.id, tool["name"])

    def _remove_routes(self, server_id: int) -> None:
        self._tool_routes = {
            name: route for name, route in self._tool_routes.items() if route[0] != server_id
        }

    @staticmethod
    def _sanitize_name(value: str) -> str:
        sanitized = "".join(char if char.isalnum() or char in "_-" else "_" for char in value)
        return sanitized or "tool"

    async def _get_server(self, server_id: int) -> McpServer | None:
        async with self.session_factory() as session:
            return await session.get(McpServer, server_id)

    async def _update_status(
        self,
        server_id: int,
        status: str,
        error: str | None,
        tools: list[dict[str, Any]],
    ) -> None:
        async with self.session_factory() as session:
            server = await session.get(McpServer, server_id)
            if server is None:
                return
            server.status = status
            server.last_error = error
            server.tools = tools
            await session.commit()
