## ADDED Requirements

### Requirement: Conversation runtime mode
The system SHALL allow an owned conversation to use `assistant`, `single_character`, or `group` mode and SHALL default existing and newly created conversations to `assistant` unless the user explicitly selects another mode.

#### Scenario: Existing conversation after migration
- **WHEN** an existing conversation is loaded after deployment
- **THEN** it behaves as a plain assistant conversation with no required character membership

#### Scenario: Select single character mode
- **WHEN** the owner selects one active owned character for a conversation
- **THEN** subsequent AI responses use that character while earlier history remains available

### Requirement: Conversation member management
The system SHALL allow the owner to add, remove, enable, disable, and order owned characters as conversation members without deleting the reusable character definitions.

#### Scenario: Add group members
- **WHEN** the owner adds two valid characters and selects group mode
- **THEN** both become ordered eligible speakers for that conversation

#### Scenario: Remove a member with history
- **WHEN** the owner removes a member that has prior messages
- **THEN** the member stops being eligible for new routing while historical speaker information remains visible

### Requirement: Conversation runtime settings
The system SHALL persist routing strategy, retrieval mode, context limits, and optional scene description per conversation and enforce ownership for all updates.

#### Scenario: Update runtime settings
- **WHEN** the owner submits valid runtime settings
- **THEN** later turns use the new settings without changing other conversations

#### Scenario: Invalid group configuration
- **WHEN** group mode is requested without any enabled member
- **THEN** the system rejects the update with a validation error

