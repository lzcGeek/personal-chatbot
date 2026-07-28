## ADDED Requirements

### Requirement: Rolling conversation summaries
The system SHALL asynchronously create versioned summaries that identify the contiguous message range they cover and SHALL preserve original messages.

#### Scenario: Compression threshold reached
- **WHEN** eligible unsummarized history exceeds the configured message or context threshold
- **THEN** a summary job is queued without blocking the current text response

#### Scenario: Summary generation fails
- **WHEN** the summary provider fails or returns invalid output
- **THEN** no incomplete summary is used and recent original history remains available

### Requirement: Scoped NPC memories
The system SHALL assign every extracted memory a scope of user, conversation-shared, or character-private and apply matching user, conversation, and character filters during retrieval.

#### Scenario: Character-private memory retrieval
- **WHEN** character A is generating a response
- **THEN** character A private memories and eligible shared memories may be retrieved while character B private memories are excluded

#### Scenario: Plain assistant conversation
- **WHEN** a legacy assistant conversation retrieves memory
- **THEN** existing conversation-scoped memories remain eligible without requiring a character

### Requirement: Memory validity and replacement
The system SHALL support importance, validity status, effective time, replacement links, and conflict reason so that superseded or unconfirmed facts are excluded from normal retrieval while provenance remains available.

#### Scenario: Preference changes
- **WHEN** the user explicitly corrects an earlier preference
- **THEN** the old memory is marked superseded and is not injected into later prompts

#### Scenario: Stateful fact changes over time
- **WHEN** a location, relationship, task, or inventory fact changes without invalidating its historical truth
- **THEN** the new fact becomes current and the previous fact remains queryable as a historical version

#### Scenario: Inferred conflict is uncertain
- **WHEN** the model detects a possible conflict that the user did not explicitly state
- **THEN** the new candidate is marked pending confirmation and neither current fact nor source messages are overwritten

#### Scenario: Facts can coexist
- **WHEN** two preferences or attributes can both be true
- **THEN** both memories remain active without a replacement link

### Requirement: Shared scene state
The system SHALL store shared NPC scene state as schema-validated data with revision and source-message provenance.

#### Scenario: Concurrent state update
- **WHEN** two updates target the same stale scene-state revision
- **THEN** the system accepts at most one update and retries or rejects the conflicting update

### Requirement: Context budget allocation
The system SHALL assemble summaries, scoped memories, scene state, evidence, and recent messages within a configured context budget using deterministic priority rules.

#### Scenario: Context exceeds budget
- **WHEN** all eligible context items cannot fit
- **THEN** platform instructions and recent messages are preserved while lower-priority memories or evidence are omitted with metrics recorded
