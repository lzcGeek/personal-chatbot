## ADDED Requirements

### Requirement: PostgreSQL memory source of truth
The system SHALL commit memory content and an outbox event atomically in PostgreSQL before indexing it in Qdrant.

#### Scenario: Qdrant unavailable
- **WHEN** Qdrant indexing fails after PostgreSQL commits a memory
- **THEN** the memory remains stored with a retryable indexing state and no data is lost

### Requirement: Filtered vector retrieval
The system SHALL query Qdrant using both the authenticated user ID and active conversation ID.

#### Scenario: Similar memory owned by another user
- **WHEN** another user's memory is semantically similar to the query
- **THEN** Qdrant filtering excludes it before results are returned

### Requirement: Vector deletion
The system SHALL enqueue vector deletion when a memory or conversation is deleted.

#### Scenario: Delete conversation
- **WHEN** a user deletes an owned conversation
- **THEN** PostgreSQL data is removed and the worker deletes matching Qdrant points by user and conversation
