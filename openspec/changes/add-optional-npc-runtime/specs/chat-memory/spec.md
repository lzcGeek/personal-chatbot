## MODIFIED Requirements

### Requirement: Semantic memory extraction
The system SHALL asynchronously extract durable facts from completed exchanges, store PostgreSQL memory records with rebuildable vector embeddings, and tag each record with owning user, conversation, scope, optional character, provenance, importance, and validity metadata.

#### Scenario: Fact extraction after conversation
- **WHEN** a conversation exchange completes
- **THEN** the system asynchronously extracts eligible facts and stores memory records plus vector-index outbox work without delaying the text response

#### Scenario: Memory retrieval scoped to conversation and speaker
- **WHEN** a new assistant or NPC response is generated
- **THEN** the system retrieves semantically relevant valid memories filtered by current user, conversation, and eligible shared or character-private scope

#### Scenario: Memory deleted with conversation
- **WHEN** a conversation is deleted
- **THEN** all memory entries, summaries, scene state, and vector index entries belonging to that conversation are permanently removed through the existing transactional/outbox deletion path

#### Scenario: Legacy memory remains eligible
- **WHEN** an existing memory has no character identifier after migration
- **THEN** it remains conversation-scoped and eligible for legacy assistant conversations

## ADDED Requirements

### Requirement: Summary checkpoint management
The system SHALL expose owned conversation summaries with covered message boundaries, status, version, creation time, and regeneration controls.

#### Scenario: List summaries
- **WHEN** the owner requests memory details for a conversation
- **THEN** completed and failed summary checkpoints are returned without exposing another user's data

#### Scenario: Regenerate a summary
- **WHEN** the owner requests regeneration for an eligible message range
- **THEN** a new version is generated and becomes active only after successful validation

### Requirement: Scoped memory management
The system SHALL allow an owner to list, invalidate, restore when safe, and delete memory records while preserving vector-index consistency.

#### Scenario: Invalidate a memory
- **WHEN** the owner marks a memory invalid
- **THEN** it is excluded from subsequent retrieval even if its vector remains temporarily present during asynchronous cleanup

#### Scenario: Cross-user memory mutation
- **WHEN** a user attempts to mutate another user's memory
- **THEN** the system returns not found and does not enqueue index work

