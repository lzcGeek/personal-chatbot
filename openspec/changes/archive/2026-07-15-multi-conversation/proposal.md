## Why

当前系统只有一个全局聊天会话，无法切换话题或保留不同场景的独立上下文。每次换话题要么污染上下文，要么只能手动清数据库。需要支持多会话——像 ChatGPT 一样的左侧会话列表。

## What Changes

- 新增 `conversations` 表，`chat_messages` 和 `memory_entries` 加 `conversation_id` 外键
- 会话 CRUD API：列表 / 新建 / 删除 / 重命名
- 聊天接口加 `conversation_id`，消息和记忆隔离到会话
- 新建一个默认会话（启动时），兼容旧消息（旧消息自动归属默认会话）
- 前端左侧新增会话侧栏：列表 + 切换 + 新建 + 删除

## Capabilities

### New Capabilities
- `conversation-management`: 会话 CRUD（列表、新建、删除、重命名），自动创建默认会话
- `chat-isolation`: 消息和语义记忆按 `conversation_id` 隔离，切换会话时上下文、历史、记忆完全独立

### Modified Capabilities
- `chat-core`: 所有聊天 API 增加 `conversation_id` 参数，流式/同步聊天均按会话隔离
- `chat-memory`: 记忆提取和检索加入 `conversation_id` 过滤，删除会话时级联删除其记忆

## Impact

- 数据库迁移：新表 + 外键列
- 后端：所有路由层、服务层、上下文构建器需加 `conversation_id`
- 前端：新增会话侧栏组件 + Pinia store 重构（当前单一 chat store 改为按会话管理）
- 旧消息兼容：无 `conversation_id` 的旧消息自动归属默认会话
