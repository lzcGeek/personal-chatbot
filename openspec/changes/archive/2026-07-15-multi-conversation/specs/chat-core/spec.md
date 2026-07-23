## MODIFIED Requirements

### Requirement: Send and receive chat messages
The system SHALL allow the user to send text messages and receive AI-generated responses via a chat interface, scoped to a specific conversation.

#### Scenario: User sends a message
- **WHEN** user types a message and presses send in a specific conversation
- **THEN** the message appears in that conversation's chat history and the system returns an AI response

#### Scenario: Empty message rejected
- **WHEN** user attempts to send an empty or whitespace-only message
- **THEN** the system ignores the input and does not call the LLM

### Requirement: Streaming response
The system SHALL stream AI responses token-by-token using Server-Sent Events (SSE), so the user sees the response appear in real time.

#### Scenario: Response streams in real time
- **WHEN** the AI generates a response
- **THEN** each token appears incrementally in the chat interface without waiting for the full response

#### Scenario: Stream interruption
- **WHEN** the SSE connection is interrupted
- **THEN** the frontend displays the partially received content and shows an error indicator

### Requirement: Multi-turn conversation context
The system SHALL maintain conversation context by sending recent chat history with each request to the LLM, limited to the current conversation.

#### Scenario: Context-aware follow-up
- **WHEN** user asks a follow-up question referencing a previous message in the same conversation
- **THEN** the AI understands the reference and responds appropriately

#### Scenario: Context window overflow
- **WHEN** the conversation history exceeds the configured token limit
- **THEN** the system truncates the oldest messages while preserving the most recent exchanges

#### Scenario: Cross-conversation isolation
- **WHEN** the user switches from conversation A to conversation B
- **THEN** messages from conversation A are excluded from the context of conversation B
