## ADDED Requirements

### Requirement: Send and receive chat messages
The system SHALL allow the user to send text messages and receive AI-generated responses via a chat interface.

#### Scenario: User sends a message
- **WHEN** user types a message and presses send
- **THEN** the message appears in the chat history and the system returns an AI response

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
The system SHALL maintain conversation context by sending recent chat history with each request to the LLM.

#### Scenario: Context-aware follow-up
- **WHEN** user asks a follow-up question referencing a previous message
- **THEN** the AI understands the reference and responds appropriately

#### Scenario: Context window overflow
- **WHEN** the conversation history exceeds the configured token limit
- **THEN** the system truncates the oldest messages while preserving the most recent exchanges

### Requirement: Markdown rendering
The frontend SHALL render AI responses as Markdown, supporting common formatting including code blocks, lists, tables, and inline code.

#### Scenario: Code block rendering
- **WHEN** the AI response contains a fenced code block
- **THEN** the frontend renders it with syntax highlighting

#### Scenario: Plain text fallback
- **WHEN** the AI response contains no Markdown formatting
- **THEN** the frontend displays it as plain text with preserved line breaks

### Requirement: LLM configuration
The system SHALL support configuring the LLM provider via environment variables, including base URL, API key, and model name.

#### Scenario: Custom LLM provider
- **WHEN** the user configures `OPENAI_BASE_URL` to a compatible API endpoint
- **THEN** the system routes all LLM requests to that endpoint

#### Scenario: Missing configuration
- **WHEN** required environment variables are not set
- **THEN** the system SHALL report a clear error message on startup
