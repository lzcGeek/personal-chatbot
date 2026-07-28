## ADDED Requirements

### Requirement: Failure classification
The system SHALL classify failures by stage and stable error code, and SHALL return a user-safe message without exposing credentials, request headers, internal URLs, stack traces, or upstream response bodies.

#### Scenario: Upstream exception contains sensitive detail
- **WHEN** an LLM, MCP, or retrieval dependency raises an exception containing internal detail
- **THEN** the client receives a mapped error code and safe message while full diagnostic context is limited to sanitized server logs

### Requirement: Transient LLM retry
The system SHALL retry an LLM request only when a configured transient failure occurs before the first response token, using bounded exponential backoff with jitter.

#### Scenario: Transient failure recovers
- **WHEN** the LLM times out, is rate limited, returns a server error, or cannot connect before emitting a token and a retry succeeds within the configured limit
- **THEN** the system returns the answer normally and records the successful retry

#### Scenario: Non-transient failure occurs
- **WHEN** the LLM returns an authentication, permission, validation, or other non-transient client error
- **THEN** the system does not retry and emits a non-recoverable structured error

### Requirement: Dependency isolation and degraded completion
The system SHALL isolate optional context and tool failures so that an answer can complete using remaining capabilities, and SHALL report which capabilities were degraded.

#### Scenario: Personal context retrieval fails
- **WHEN** memory or personal-document retrieval fails
- **THEN** the system continues without the failed source and includes its stable degradation code in the completed event

#### Scenario: Network tool fails
- **WHEN** an allowed network tool times out, disconnects, or returns an error
- **THEN** the model receives a structured failure result and may complete from local context while clearly stating that online retrieval failed

#### Scenario: Tool-call rounds are exhausted
- **WHEN** the model reaches the configured maximum tool-call rounds
- **THEN** the system makes one final tool-disabled synthesis attempt using results already collected instead of immediately failing the request

### Requirement: Stream interruption preservation
The system SHALL preserve content emitted before a stream interruption and SHALL not automatically replay a partially emitted generation.

#### Scenario: Stream fails after tokens were emitted
- **WHEN** an exception occurs after at least one assistant token has been emitted
- **THEN** the partial assistant message is persisted with `interrupted` status and the error event states that partial content was saved

#### Scenario: User retries an interrupted request
- **WHEN** the frontend retries a recoverable interrupted request
- **THEN** it replays the original message and network permission with an idempotency identifier so the user message is not duplicated

### Requirement: Fallback observability
The system SHALL record structured, sanitized telemetry for retries, degradation, network-tool latency, terminal errors, and request outcome.

#### Scenario: A request completes with degradation
- **WHEN** any optional capability fails but the answer completes
- **THEN** the system records the request identifier, degradation codes, stage durations, and final outcome without recording protected request content

