## ADDED Requirements

### Requirement: Per-document graph indexing mode
The system SHALL accept `inherit`, `enabled`, or `disabled` as the graph indexing mode when a document is uploaded while always performing the supported text/vector indexing path.

#### Scenario: Graph disabled at upload
- **WHEN** a user uploads a document with graph mode `disabled`
- **THEN** the document becomes text-searchable without enqueueing graph extraction and displays graph status as skipped

#### Scenario: Graph enabled but unavailable
- **WHEN** graph mode resolves to enabled while Neo4j is unavailable
- **THEN** text/vector indexing can complete and graph status reports a recoverable failure or unavailable state

#### Scenario: Legacy upload request
- **WHEN** an existing client uploads without a graph mode
- **THEN** the system uses `inherit` and preserves the configured legacy behavior

### Requirement: Deferred graph build and rebuild
The system SHALL allow an owner to request graph construction or reconstruction for a text-ready document using an idempotent asynchronous job.

#### Scenario: Build a previously skipped graph
- **WHEN** the owner enables graph indexing for a skipped text-ready document
- **THEN** one current-revision graph job is queued and document text remains searchable

#### Scenario: Duplicate build request
- **WHEN** an equivalent current-revision graph job is already active
- **THEN** the system does not create duplicate graph facts or concurrent duplicate work

### Requirement: Conversation retrieval mode
The system SHALL support `auto`, `off`, `vector`, and `hybrid` retrieval modes per conversation.

#### Scenario: Retrieval off
- **WHEN** a conversation uses retrieval mode `off`
- **THEN** neither document embeddings nor document graph are queried

#### Scenario: Vector-only retrieval
- **WHEN** a conversation uses retrieval mode `vector`
- **THEN** vector document evidence may be retrieved and Neo4j is not queried

#### Scenario: Hybrid graph degradation
- **WHEN** hybrid retrieval is selected and graph retrieval fails
- **THEN** available vector evidence is used and the response reports a graph retrieval degradation

### Requirement: Graph control ownership
The system MUST enforce current-user ownership for graph mode changes, builds, rebuilds, status, and retrieval filters.

#### Scenario: Build another user's document graph
- **WHEN** a user requests a graph operation for a document they do not own
- **THEN** the system returns not found and does not enqueue work

