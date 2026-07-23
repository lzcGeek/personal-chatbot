## ADDED Requirements

### Requirement: Messages isolated by conversation
The system SHALL isolate chat messages per conversation so that switching conversations shows only the relevant history.

#### Scenario: Switch conversation shows different messages
- **WHEN** the user switches from conversation A to conversation B
- **THEN** the chat window shows only messages belonging to conversation B

#### Scenario: New message saved to current conversation
- **WHEN** the user sends a message in conversation A
- **THEN** the message is associated with conversation A and does not appear in other conversations

### Requirement: Memories isolated by conversation
The system SHALL isolate semantic memories per conversation, retrieving only memories relevant to the active session.

#### Scenario: Memory search scoped to conversation
- **WHEN** the user sends a message in conversation A
- **THEN** only memories belonging to conversation A are retrieved and injected into the context

#### Scenario: Memory stored with conversation ID
- **WHEN** a new memory is extracted after an assistant response
- **THEN** the memory is tagged with the current conversation ID

### Requirement: Legacy data migration
The system SHALL handle existing messages and memories that lack a conversation ID by assigning them to a default conversation.

#### Scenario: Old messages get default conversation
- **WHEN** the application starts with existing messages that have no conversation_id
- **THEN** those messages are automatically assigned to a newly created default conversation
