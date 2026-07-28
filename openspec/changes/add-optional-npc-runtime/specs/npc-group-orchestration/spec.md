## ADDED Requirements

### Requirement: Deterministic speaker plan
The system SHALL resolve each NPC turn into an ordered speaker plan containing only enabled members of the current conversation.

#### Scenario: Manual speaker selection
- **WHEN** the user selects an enabled conversation member
- **THEN** only that member is placed in the speaker plan

#### Scenario: Mention routing
- **WHEN** mention routing is active and the message uniquely mentions an enabled member
- **THEN** the mentioned member is selected

#### Scenario: Round-robin routing
- **WHEN** round-robin routing is active without an explicit speaker
- **THEN** the next enabled member after the previous NPC speaker is selected

### Requirement: Bounded automatic routing
The system SHALL constrain automatic routing to current member identifiers and configured per-turn speaker and generation limits.

#### Scenario: Router returns an unknown character
- **WHEN** the routing model returns an identifier outside the allowed member set
- **THEN** the system rejects that choice and applies the configured safe fallback

#### Scenario: Speaker limit reached
- **WHEN** the plan would exceed the maximum speakers for one user turn
- **THEN** additional speakers are omitted and a bounded routing result is recorded

### Requirement: Ordered NPC generation
The system SHALL generate and persist planned NPC responses in speaker-plan order, exposing the active speaker in stream events.

#### Scenario: Two NPCs respond
- **WHEN** a valid plan contains two speakers
- **THEN** the first response is persisted before the second response is generated and each message records its speaker

#### Scenario: One NPC generation fails
- **WHEN** a later planned NPC fails after an earlier response completed
- **THEN** completed messages remain persisted and the stream reports which speaker failed

### Requirement: Orchestration observability
The system SHALL record the routing strategy, selected speakers, fallback reason, duration, and bounded usage without storing hidden model reasoning.

#### Scenario: Automatic route completes
- **WHEN** automatic routing selects a speaker
- **THEN** the system stores the selection metadata and a concise machine-readable reason code

