## MODIFIED Requirements

### Requirement: Send and receive chat messages
The system SHALL allow the user to send text messages with per-request generation options and receive AI-generated responses via a chat interface. Retrying the same client request identifier SHALL not create a duplicate user message in the same conversation.

#### Scenario: User sends a message
- **WHEN** user types a message, selects generation options, and presses send
- **THEN** the message appears in the chat history and the system returns an AI response using the captured options

#### Scenario: Empty message rejected
- **WHEN** user attempts to send an empty or whitespace-only message
- **THEN** the system ignores the input and does not call the LLM

#### Scenario: Client retries the same request
- **WHEN** the same authenticated user repeats a chat request in the same conversation with an existing client request identifier
- **THEN** the system reuses the persisted user-message operation instead of adding a duplicate user message

### Requirement: Streaming response
The system SHALL stream AI responses token-by-token using Server-Sent Events (SSE), so the user sees the response appear in real time, and SHALL represent completion, degradation, and terminal failure with stable structured fields.

#### Scenario: Response streams in real time
- **WHEN** the AI generates a response
- **THEN** each token appears incrementally in the chat interface without waiting for the full response

#### Scenario: Response completes with degraded capability
- **WHEN** the answer completes while an optional retrieval or tool capability was unavailable
- **THEN** the `done` event includes the saved message, `degraded=true`, and stable degradation codes

#### Scenario: Stream interruption
- **WHEN** the SSE generation is interrupted
- **THEN** the frontend displays the partially received content and a structured error containing a stable code, safe message, recoverability flag, request identifier, and partial-save state

