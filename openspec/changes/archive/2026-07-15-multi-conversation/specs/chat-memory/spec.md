## MODIFIED Requirements

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
