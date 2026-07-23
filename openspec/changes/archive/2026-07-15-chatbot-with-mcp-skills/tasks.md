## 1. Project Scaffolding

- [x] 1.1 Initialize backend project: create `backend/` directory with `pyproject.toml` (FastAPI, uvicorn, SQLAlchemy, ChromaDB, openai, mcp SDK)
- [x] 1.2 Initialize frontend project: create `frontend/` directory with Vue 3 + Vite + Pinia
- [x] 1.3 Create root-level `.env.example` with LLM config variables (OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL)
- [x] 1.4 Create `skills/` directory with an example skill (e.g., `skills/example/SKILL.md`)
- [x] 1.5 Configure Vite dev server proxy to backend at port 8021

## 2. Backend Core

- [x] 2.1 Implement config loading from environment variables (`backend/app/core/config.py`)
- [x] 2.2 Set up SQLAlchemy async engine + session with SQLite (`backend/app/core/database.py`)
- [x] 2.3 Define ORM models: ChatMessage, McpServer, MemoryEntry (`backend/app/models/`)
- [x] 2.4 Create database init script that creates tables on startup
- [x] 2.5 Implement FastAPI app entry point with CORS middleware (`backend/app/main.py`)

## 3. Chat API

- [x] 3.1 Implement LLM client wrapper using OpenAI SDK (`backend/app/services/llm_client.py`)
- [x] 3.2 Implement chat send endpoint POST /api/chat/send — saves user message, builds context, calls LLM, saves response
- [x] 3.3 Implement streaming endpoint POST /api/chat/stream — SSE streaming with token-by-token output
- [x] 3.4 Implement GET /api/chat/history — paginated chat message loading
- [x] 3.5 Implement chat context builder — assembles system prompt + recent messages + memory + MCP tools + skills

## 4. Memory System

- [x] 4.1 Initialize ChromaDB embedded client (`backend/app/services/memory_service.py`)
- [x] 4.2 Implement async memory extraction — after each AI response, extract key facts and store as vector embeddings
- [x] 4.3 Implement memory retrieval — query ChromaDB for relevant memories on each new user message
- [x] 4.4 Implement GET /api/memories — list all stored memories
- [x] 4.5 Implement DELETE /api/memories/{id} — delete a memory entry

## 5. MCP Integration

- [x] 5.1 Define MCP Server config model + DB table (`backend/app/models/mcp_server.py`)
- [x] 5.2 Implement MCP connection manager — connect/disconnect/reconnect with auto-retry (`backend/app/services/mcp_manager.py`)
- [x] 5.3 Implement tool discovery — on connect, call tools/list and cache tool schemas
- [x] 5.4 Implement POST /api/mcp/servers — add and connect a new MCP Server
- [x] 5.5 Implement GET /api/mcp/servers — list all servers with status and tools
- [x] 5.6 Implement DELETE /api/mcp/servers/{id} — disconnect and remove a server
- [x] 5.7 Implement tool call execution in chat flow — detect LLM tool_call, execute via MCP, feed result back to LLM

## 6. Skill System

- [x] 6.1 Implement skill loader — scan `skills/` directory, parse SKILL.md frontmatter + content (`backend/app/services/skill_loader.py`)
- [x] 6.2 Implement skill injection into system prompt — append skill contents under "Skills" section
- [x] 6.3 Implement GET /api/skills — list all loaded skills
- [x] 6.4 Implement POST /api/skills/reload — hot-reload skills from disk

## 7. Frontend Chat Interface

- [x] 7.1 Set up Vue 3 project structure: components, stores, api layer (`frontend/src/`)
- [x] 7.2 Implement Axios API layer with base URL `/api` (`frontend/src/api/`)
- [x] 7.3 Implement Pinia chat store — messages state, send message action, stream handling (`frontend/src/stores/chat.ts`)
- [x] 7.4 Implement ChatWindow component — message list with auto-scroll, message bubbles (user vs AI)
- [x] 7.5 Implement ChatInput component — text input with send button, Enter to send
- [x] 7.6 Implement MessageBubble component — Markdown rendering with code syntax highlighting
- [x] 7.7 Implement streaming display — SSE consumption with incremental text rendering
- [x] 7.8 Implement infinite scroll history loading in ChatWindow

## 8. Integration & Polish

- [x] 8.1 Wire up full chat flow: user input → API call → streaming display → memory extraction
- [x] 8.2 Add error handling UI — display error toasts for network failures, LLM errors
- [x] 8.3 Add loading states — typing indicator while LLM is generating
- [x] 8.4 Test end-to-end: send messages, verify history persists across page refresh, verify memory recall works
