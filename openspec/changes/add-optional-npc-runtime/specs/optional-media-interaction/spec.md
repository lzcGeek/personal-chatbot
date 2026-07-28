## ADDED Requirements

### Requirement: Optional provider capability registry
The system SHALL expose configured image and TTS capabilities without exposing provider secrets and SHALL operate normally when neither capability is configured.

#### Scenario: No media providers configured
- **WHEN** the application starts without image or TTS providers
- **THEN** text chat remains available and media controls are disabled or hidden with an explanatory status

#### Scenario: List provider capabilities
- **WHEN** an authenticated user requests media capabilities
- **THEN** the system returns allowed provider/profile identifiers and limits without returning API keys

### Requirement: Text-first media generation
The system SHALL persist a complete assistant text message before starting optional image or TTS generation for that message.

#### Scenario: TTS generation succeeds
- **WHEN** TTS is requested for a completed assistant message
- **THEN** an audio attachment is linked to that message and a completion event is emitted

#### Scenario: Image generation fails
- **WHEN** an image provider fails after the text response completed
- **THEN** the text message remains complete and only the media task is marked failed with a retryable error when applicable

### Requirement: Authorized character media profiles
The system SHALL resolve a character's voice and image defaults only against server-allowed provider profiles and user-accessible conversation data.

#### Scenario: Unknown voice profile
- **WHEN** a character references a voice profile that is no longer available
- **THEN** TTS is skipped or rejected without falling back to an unintended voice

### Requirement: Private validated attachments
The system SHALL authorize attachment access by owning user and validate generated media MIME type, size, storage path, and task provenance.

#### Scenario: Cross-user attachment access
- **WHEN** a user requests another user's generated attachment
- **THEN** the system returns not found without exposing storage metadata

#### Scenario: Provider returns oversized media
- **WHEN** provider output exceeds the configured limit
- **THEN** the output is rejected and not attached to the message

### Requirement: Bounded media requests
The system SHALL enforce configured timeouts, per-message generation limits, and request idempotency for image and TTS jobs.

#### Scenario: Duplicate TTS request
- **WHEN** the same idempotency key is retried for a message and voice profile
- **THEN** the existing task or attachment is returned instead of generating duplicate audio

