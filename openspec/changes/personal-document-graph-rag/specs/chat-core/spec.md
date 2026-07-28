## MODIFIED Requirements

### Requirement: Send and receive chat messages
The system SHALL allow the authenticated user to send text messages and receive AI-generated responses via a chat interface, using relevant user-owned document evidence when available and returning structured citations with the response.

#### Scenario: User sends a message
- **WHEN** user types a message and presses send
- **THEN** the message appears in the chat history and the system returns an AI response

#### Scenario: Relevant personal document
- **WHEN** the user's ready knowledge documents contain relevant evidence
- **THEN** the system retrieves that evidence before generation and returns source citations for material document-derived claims

#### Scenario: Empty message rejected
- **WHEN** user attempts to send an empty or whitespace-only message
- **THEN** the system ignores the input and does not call the LLM
