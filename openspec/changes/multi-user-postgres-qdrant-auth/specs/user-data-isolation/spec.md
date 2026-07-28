## ADDED Requirements

### Requirement: User-owned resources
The system SHALL restrict conversations, messages, memories and MCP servers to their owning user.

#### Scenario: Cross-user resource ID
- **WHEN** user A submits the identifier of a resource owned by user B
- **THEN** the system responds as though the resource does not exist and does not read or modify it

### Requirement: Mandatory conversation ownership
The system SHALL require every chat operation to use a conversation owned by the authenticated user.

#### Scenario: Missing conversation
- **WHEN** an authenticated user sends or loads chat without a valid owned conversation
- **THEN** the system rejects the request instead of using global history
