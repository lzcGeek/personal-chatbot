## ADDED Requirements

### Requirement: Structure-aware parsing
The system SHALL preserve available document structure such as page number, heading, paragraph order and source filename while extracting text.

#### Scenario: PDF page provenance
- **WHEN** a text PDF is parsed
- **THEN** every resulting chunk retains its source document and page number

### Requirement: Sentence-window indexing
The system SHALL index focused text chunks for semantic precision while retaining adjacent context for answer generation.

#### Scenario: Chunk retrieved
- **WHEN** a focused chunk matches a user query
- **THEN** the retriever can provide its expanded context window without embedding the window as the point vector

### Requirement: Isolated document collection
The system SHALL store document vectors in a Qdrant Collection separate from conversation memories and include user, document, chunk and revision payload fields.

#### Scenario: Vector search
- **WHEN** the system searches personal documents
- **THEN** Qdrant filters by the authenticated user and excludes deleting or deleted documents before returning candidates

### Requirement: Rebuildable vector index
The system SHALL treat PostgreSQL chunks as the source of truth and support idempotent vector upsert and deletion.

#### Scenario: Qdrant data lost
- **WHEN** the document Collection is recreated
- **THEN** all ready PostgreSQL chunks can be re-embedded and indexed without re-uploading files
