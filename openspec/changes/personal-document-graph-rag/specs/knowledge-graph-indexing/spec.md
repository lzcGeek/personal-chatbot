## ADDED Requirements

### Requirement: Provenance-aware graph extraction
The system SHALL extract entities and facts from document chunks while preserving user, document, chunk, source text and confidence provenance.

#### Scenario: Fact extracted
- **WHEN** a chunk contains an entity relationship supported by its text
- **THEN** the graph stores a traceable Fact connected to normalized Entity nodes

### Requirement: Entity normalization
The system SHALL normalize labels and aliases within a user's graph without merging entities across users.

#### Scenario: Shared alias in two users
- **WHEN** two users upload documents containing the same entity name
- **THEN** their graph nodes and facts remain isolated by user ownership

### Requirement: Graph deletion by source
The system SHALL delete only facts and chunks contributed by the deleted document and SHALL preserve entities or facts still supported by other documents.

#### Scenario: Shared entity remains referenced
- **WHEN** a deleted document and a retained document both mention the same entity
- **THEN** the retained document's facts and required Entity node remain available

### Requirement: Graph service degradation
The system SHALL continue document vector retrieval when Neo4j is unavailable and SHALL expose graph indexing as pending or failed.

#### Scenario: Neo4j unavailable during query
- **WHEN** vector evidence is available but graph retrieval fails
- **THEN** the system answers from vector evidence and does not claim graph-derived facts
