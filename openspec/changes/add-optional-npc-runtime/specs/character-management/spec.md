## ADDED Requirements

### Requirement: User-owned character lifecycle
The system SHALL allow an authenticated user to create, view, update, duplicate, archive, and delete only their own characters.

#### Scenario: Create a character
- **WHEN** a user submits a valid character name and optional definition fields
- **THEN** the system creates a user-owned character and returns its identifier

#### Scenario: Cross-user access is rejected
- **WHEN** a user requests or modifies a character owned by another user
- **THEN** the system returns not found without disclosing the character

#### Scenario: Delete a character referenced by history
- **WHEN** a user deletes a character that is referenced by persisted messages
- **THEN** the character is archived or soft-deleted and historical speaker snapshots remain readable

### Requirement: Structured character definition
The system SHALL store character identity, avatar, description, personality, scenario, greeting, example dialogue, generation settings, tool permissions, and optional image/TTS profile as distinct validated fields.

#### Scenario: Invalid generation setting
- **WHEN** a character update contains a generation value outside the server-defined range
- **THEN** the update is rejected with a validation error

#### Scenario: Optional fields omitted
- **WHEN** a user creates a character with only a name
- **THEN** the system applies safe defaults and the character can be used in a conversation

### Requirement: Character permissions cannot elevate platform permissions
The system MUST calculate effective network, MCP, knowledge, and media permissions as the intersection of server, user request, conversation, and character permissions.

#### Scenario: Character requests an unavailable tool
- **WHEN** a character definition names a tool that is not authorized for the user or request
- **THEN** the tool is excluded from the model context and rejected at execution

### Requirement: Character avatar handling
The system SHALL validate avatar ownership, supported MIME type, size, and storage path before displaying it.

#### Scenario: Valid avatar upload
- **WHEN** a user uploads a supported avatar within the size limit
- **THEN** the avatar is stored under the user's private namespace and linked to the character

