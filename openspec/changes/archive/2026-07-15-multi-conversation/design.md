## Context

当前架构：单一全局聊天流。需要改为多会话模式，每个会话有独立的 messages + memories。前端布局改为三栏：会话侧栏 | 聊天区 | 设置面板。

## Goals / Non-Goals

**Goals:**
- 会话 CRUD（列表、新建、删除、重命名）
- 消息按 `conversation_id` 完全隔离
- 记忆按 `conversation_id` 隔离，切换会话时检索不同记忆库
- 默认会话兼容旧数据
- 左侧固定侧栏，可折叠

**Non-Goals:**
- 会话导出/导入
- 会话搜索
- 会话固定/归档

## Decisions

### 1. 数据模型：外键级联
- `conversations(id, title, created_at, updated_at)`
- `chat_messages.conversation_id` → FK → `conversations.id`
- `memory_entries.conversation_id` → FK → `conversations.id`
- 删会话 → 级联删消息和记忆

### 2. 默认会话：启动时自动创建
- 无旧数据时新建 "新对话"
- 有旧消息但无 `conversation_id`：迁移脚本将其全部归属到一个新的默认会话

### 3. 前端布局：左侧会话栏
```
┌──────────┬─────────────────────┬──────────┐
│ 会话列表  │      聊天区          │  设置面板 │
│ + 新建    │  messages           │  (已有的) │
│ 会话1     │  input              │          │
│ 会话2 ←   │                     │          │
└──────────┴─────────────────────┴──────────┘
```
- 会话栏固定 240px，可折叠
- 当前会话高亮
- 列表按 `updated_at` 倒序

### 4. Pinia Store：拆分为 `conversationStore` + `chatStore`
- `conversationStore`：会话列表、当前 ID、切换
- `chatStore`：当前会话的消息/流式状态，依赖 `conversationStore.currentId`

### 5. API 改动：所有聊天接口加 `conversation_id`
- `POST /api/chat/send` + `POST /api/chat/stream`：body 加 `conversation_id`
- `GET /api/chat/history`：query 加 `conversation_id`
- `POST /api/conversations`：新建会话
- `GET /api/conversations`：列表
- `DELETE /api/conversations/{id}`：删除（级联）
- `PATCH /api/conversations/{id}`：重命名

### 6. ChromaDB 隔离：metadata 过滤
- 写入时 `metadata["conversation_id"] = str(conversation_id)`
- 检索时 `collection.get(where={"conversation_id": conversation_id})`

## Risks / Trade-offs

- **[R] 旧数据兼容**：迁移脚本需处理多种情况（空库、有消息无会话）→ 默认会话兜底
- **[R] ChromaDB metadata 过滤 vs 新 collection**：选 metadata 过滤更轻量，但性能略差 → 当前规模无影响
- **[R] 前端 store 拆分**：从单一 chat store 拆为两个 → 导入路径要改，但改动集中
