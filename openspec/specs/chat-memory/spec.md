## Requirements

### Requirement: Chat history persistence
The system SHALL persist all chat messages to the database, including user messages and AI responses, with timestamps.

#### Scenario: Messages saved automatically
- **WHEN** a message is sent or received
- **THEN** it is persisted to the database with a timestamp before the response is returned

#### Scenario: History survives restart
- **WHEN** the application restarts
- **THEN** all previous chat messages are still available and displayed in the chat interface

### Requirement: Chat history loading
The system SHALL load and display recent chat history when the user opens the chat page.

#### Scenario: Recent messages visible on load
- **WHEN** the user opens the chat page
- **THEN** the most recent N messages are loaded and displayed, with infinite scroll to load older messages

### Requirement: Semantic memory extraction
The system SHALL extract key facts from conversations and store them as vector embeddings, tagged with the current conversation ID for per-conversation retrieval.

#### Scenario: Fact extraction after conversation
- **WHEN** a conversation exchange completes
- **THEN** the system asynchronously extracts key facts and stores them as vector embeddings in ChromaDB with the conversation ID

#### Scenario: Memory retrieval scoped to conversation
- **WHEN** the user sends a new message
- **THEN** the system queries ChromaDB for semantically relevant memories filtered by the current conversation ID

#### Scenario: Memory deleted with conversation
- **WHEN** a conversation is deleted
- **THEN** all memory entries and their ChromaDB vectors belonging to that conversation are permanently removed

### Requirement: Memory relevance scoring
The system SHALL retrieve only memories above a relevance threshold to avoid noise in the conversation context.

#### Scenario: Irrelevant memory excluded
- **WHEN** retrieved memories have similarity scores below the configured threshold
- **THEN** those memories are excluded from the LLM context

#### Scenario: Relevant memory included
- **WHEN** retrieved memories have similarity scores above the configured threshold
- **THEN** they are formatted and prepended to the system prompt as relevant context

### Requirement: Memory management
The system SHALL provide API endpoints to list and delete stored memories.

#### Scenario: List all memories
- **WHEN** the user calls GET /api/memories
- **THEN** the system returns all stored memory entries with their metadata

#### Scenario: Delete a memory
- **WHEN** the user calls DELETE /api/memories/{id}
- **THEN** the specified memory entry and its vector embedding are permanently removed
