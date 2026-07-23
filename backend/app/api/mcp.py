from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.mcp_server import McpServer
from app.schemas.mcp import McpServerCreate


router = APIRouter(prefix="/api/mcp/servers", tags=["mcp"])


def serialize_server(server: McpServer) -> dict[str, object]:
    return {
        "id": server.id,
        "name": server.name,
        "transport": server.transport,
        "command": server.command,
        "args": server.args,
        "url": server.url,
        "header_keys": sorted((server.headers or {}).keys()),
        "env_keys": sorted((server.env or {}).keys()),
        "status": server.status,
        "enabled": server.enabled,
        "last_error": server.last_error,
        "tools": server.tools,
        "created_at": server.created_at.isoformat(),
        "updated_at": server.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_server(payload: McpServerCreate, request: Request) -> dict[str, object]:
    if payload.transport == "stdio":
        try:
            request.app.state.mcp_manager._validate_stdio_command(payload.command)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    server = McpServer(
        name=payload.name.strip(),
        transport=payload.transport,
        command=payload.command,
        args=payload.args,
        url=str(payload.url) if payload.url else None,
        headers=payload.headers,
        env=payload.env,
    )
    try:
        async with SessionLocal() as session:
            session.add(server)
            await session.commit()
            await session.refresh(server)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="MCP server name already exists") from exc

    try:
        await request.app.state.mcp_manager.connect_and_wait(server)
    except RuntimeError as exc:
        await request.app.state.mcp_manager.stop(server.id)
        async with SessionLocal() as session:
            failed = await session.get(McpServer, server.id)
            if failed is not None:
                await session.delete(failed)
                await session.commit()
        raise HTTPException(status_code=422, detail=f"MCP validation failed: {exc}") from exc

    async with SessionLocal() as session:
        connected = await session.get(McpServer, server.id)
        return serialize_server(connected)


@router.get("")
async def list_servers() -> dict[str, list[dict[str, object]]]:
    async with SessionLocal() as session:
        result = await session.execute(select(McpServer).order_by(McpServer.created_at))
        servers = list(result.scalars())
    return {"servers": [serialize_server(server) for server in servers]}


@router.post("/{server_id}/enable")
async def enable_server(server_id: int, request: Request) -> dict[str, object]:
    if not await request.app.state.mcp_manager.set_enabled(server_id, True):
        raise HTTPException(status_code=404, detail="MCP server not found")
    return {"id": server_id, "enabled": True}


@router.post("/{server_id}/disable")
async def disable_server(server_id: int, request: Request) -> dict[str, object]:
    if not await request.app.state.mcp_manager.set_enabled(server_id, False):
        raise HTTPException(status_code=404, detail="MCP server not found")
    return {"id": server_id, "enabled": False}


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: int, request: Request) -> None:
    async with SessionLocal() as session:
        server = await session.get(McpServer, server_id)
        if server is None:
            raise HTTPException(status_code=404, detail="MCP server not found")
    await request.app.state.mcp_manager.stop(server_id)
    async with SessionLocal() as session:
        server = await session.get(McpServer, server_id)
        if server is not None:
            await session.delete(server)
            await session.commit()
