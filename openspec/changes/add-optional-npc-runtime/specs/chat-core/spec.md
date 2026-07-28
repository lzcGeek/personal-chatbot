## ADDED Requirements

### Requirement: Backward-compatible NPC chat request
The system SHALL accept existing chat requests unchanged and SHALL accept optional target speaker and media preferences only when the conversation mode supports them.

#### Scenario: Legacy request in assistant mode
- **WHEN** a client sends the existing message, conversation ID, network flag, and request ID fields
- **THEN** the system produces one assistant response using the existing behavior

#### Scenario: Invalid target speaker
- **WHEN** a request targets a character that is not an enabled member of the conversation
- **THEN** the system rejects the target without generating a response

### Requirement: Speaker-attributed messages
The system SHALL persist and return character identifier and immutable speaker-name snapshot for NPC messages while allowing both fields to be absent on legacy assistant messages.

#### Scenario: Character response saved
- **WHEN** an NPC response completes
- **THEN** the message contains the selected character ID and the speaker name used at generation time

#### Scenario: Character renamed later
- **WHEN** a character is renamed after earlier messages were created
- **THEN** historical messages retain their original speaker-name snapshot

### Requirement: Layered character context
The system SHALL build each NPC request using platform constraints, effective permissions, scene state, current character definition, scoped memory, evidence, summaries, and recent messages in deterministic priority order.

#### Scenario: Character definition contains tool instructions
- **WHEN** a character definition asks to use a tool that is not effectively authorized
- **THEN** the tool is unavailable and execution remains rejected even if the model requests it

#### Scenario: Context budget is exhausted
- **WHEN** optional context layers exceed the request budget
- **THEN** platform constraints and recent conversation content are retained according to the configured priority policy

### Requirement: NPC streaming events
The system SHALL identify the current speaker in routing, speaker-start, token, speaker-done, media-status, and error SSE events while retaining compatibility with existing token and done consumers.

#### Scenario: Group response streams
- **WHEN** two planned NPC responses are generated
- **THEN** events delimit each speaker and tokens can be associated with the correct message

#### Scenario: Legacy client consumes stream
- **WHEN** a client ignores unknown event fields or event types
- **THEN** it can still render text tokens and terminal completion for a single assistant response

### Requirement: NPC response idempotency
The system SHALL prevent a retried client request from creating duplicate user messages, speaker plans, NPC responses, or automatic media tasks.

#### Scenario: Group request is retried
- **WHEN** the same client request ID is submitted again after the original plan partially or fully completed
- **THEN** the system returns or resumes the persisted result without duplicating completed messages

