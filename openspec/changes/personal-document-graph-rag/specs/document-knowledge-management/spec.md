## ADDED Requirements

### Requirement: Authenticated document upload
The system SHALL allow an authenticated user to upload supported PDF, DOCX, TXT and Markdown files while rejecting unsupported, oversized or invalid files.

#### Scenario: Supported document accepted
- **WHEN** an authenticated user uploads a valid supported document
- **THEN** the system stores the file under a generated document identifier and returns a processing status

#### Scenario: Invalid upload rejected
- **WHEN** a file exceeds the configured limit or its content does not match a supported type
- **THEN** the system rejects it without creating an index job

### Requirement: User-owned document lifecycle
The system SHALL scope document listing, status, content metadata and deletion to the authenticated owner.

#### Scenario: Cross-user document identifier
- **WHEN** user A requests or deletes a document owned by user B
- **THEN** the system responds as though the document does not exist

### Requirement: Durable processing state
The system SHALL expose uploaded, processing, ready, failed, deleting and deleted document states with a retry-safe error record.

#### Scenario: Parser failure
- **WHEN** parsing or indexing a document fails
- **THEN** the document remains recorded as failed with an actionable error and can be retried without duplicate chunks

### Requirement: Complete document deletion
The system SHALL eventually delete the original file, PostgreSQL chunks, Qdrant points and Neo4j facts associated with the owner's document.

#### Scenario: Delete partially fails
- **WHEN** one external store is temporarily unavailable during deletion
- **THEN** the document remains excluded from retrieval and deletion is retried until every store is cleaned
