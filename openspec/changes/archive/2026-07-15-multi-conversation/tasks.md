## 1. Database & Models

- [x] 1.1 Create `Conversation` ORM model
- [x] 1.2 Add `conversation_id` FK column to `ChatMessage` and `MemoryEntry` models
- [x] 1.3 Add migration logic to `init_database()` for new columns and legacy data assignment

## 2. Backend — Conversation API

- [x] 2.1 Add `POST /api/conversations` — create new conversation with auto title
- [x] 2.2 Add `GET /api/conversations` — list all conversations ordered by updated_at
- [x] 2.3 Add `DELETE /api/conversations/{id}` — delete with cascade, prevent deleting last
- [x] 2.4 Add `PATCH /api/conversations/{id}` — rename conversation

## 3. Backend — Chat & Memory Isolation

- [x] 3.1 Modify `POST /api/chat/send` and `POST /api/chat/stream` to accept and use `conversation_id`
- [x] 3.2 Modify `GET /api/chat/history` to filter by `conversation_id` query param
- [x] 3.3 Update `ContextBuilder.build()` to scope messages to `conversation_id`
- [x] 3.4 Update `MemoryService` search/store to filter by `conversation_id` via ChromaDB metadata
- [x] 3.5 Cascade-delete ChromaDB vectors when deleting a conversation

## 4. Frontend — Conversation Sidebar

- [x] 4.1 Create `ConversationSidebar.vue` — list with active highlight, new/delete buttons
- [x] 4.2 Create `useConversationStore` Pinia store — list / currentId / switch / create / delete
- [x] 4.3 Refactor `useChatStore` to depend on `conversationStore.currentId` for message loading
- [x] 4.4 Update `ChatWindow.vue` layout to include sidebar (three-column: sidebar | chat | settings)
- [x] 4.5 Add collapse/expand toggle for sidebar

## 5. Polish

- [x] 5.1 Handle last-conversation edge case (auto-create new one before delete)
- [x] 5.2 Auto-update conversation `updated_at` on new message
- [x] 5.3 Verify: create 3 conversations, chat in each, switch between them, confirm messages don't leak
