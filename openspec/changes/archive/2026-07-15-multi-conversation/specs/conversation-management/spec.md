## ADDED Requirements

### Requirement: Create conversation
The system SHALL support creating a new conversation with an auto-generated title.

#### Scenario: Create new conversation
- **WHEN** the user clicks "新建会话"
- **THEN** a new conversation is created with title "新对话" and becomes the active session

#### Scenario: Default conversation on first launch
- **WHEN** the application starts with no existing conversations
- **THEN** a default conversation is automatically created

### Requirement: List conversations
The system SHALL return all conversations ordered by last activity.

#### Scenario: List with most recent first
- **WHEN** the user opens the conversation sidebar
- **THEN** conversations are displayed in reverse chronological order of `updated_at`

#### Scenario: Current conversation highlighted
- **WHEN** viewing the conversation list
- **THEN** the currently active conversation is visually distinguished

### Requirement: Delete conversation
The system SHALL support deleting a conversation and all its associated data.

#### Scenario: Delete with cascade
- **WHEN** the user deletes a conversation
- **THEN** all messages and memory entries belonging to that conversation are permanently removed

#### Scenario: Cannot delete last conversation
- **WHEN** the user attempts to delete the only remaining conversation
- **THEN** the system creates a new default conversation before allowing deletion

### Requirement: Rename conversation
The system SHALL support renaming a conversation.

#### Scenario: Rename via API
- **WHEN** the user sends PATCH /api/conversations/{id} with a new title
- **THEN** the conversation title is updated
