## ADDED Requirements

### Requirement: Per-request network permission
The system SHALL accept an explicit network-tool permission for every chat request and SHALL treat an omitted permission as denied.

#### Scenario: User enables network access
- **WHEN** the user sends a message with `allow_network` set to true
- **THEN** the system may expose and execute eligible network tools for that request

#### Scenario: User leaves network access disabled
- **WHEN** the user sends a message with `allow_network` set to false or omits the field
- **THEN** the system excludes network tools from that request while continuing with local conversation, memory, and personal-document context

### Requirement: Server-side network enforcement
The system MUST enforce network permission both when constructing the model tool list and immediately before executing a tool classified as requiring network access.

#### Scenario: Model receives tools while networking is disabled
- **WHEN** context is built for a request that does not allow network access
- **THEN** no tool belonging to a network-classified MCP server is included in the model request

#### Scenario: Network tool execution is attempted without permission
- **WHEN** a network-classified tool reaches the execution layer for a request that does not allow network access
- **THEN** the system rejects the invocation with the stable error code `network_access_denied` and does not enqueue or call the tool

### Requirement: Network control in the composer
The frontend SHALL provide a network toggle in the message composer, show its current state before sending, and send the captured state with the message.

#### Scenario: Toggle state is changed
- **WHEN** the user changes the network toggle and sends a message
- **THEN** the request contains the displayed state and the state used by retry remains attached to that message

#### Scenario: No preference has been stored
- **WHEN** a user opens the composer without a previously stored preference
- **THEN** the network toggle is off

### Requirement: Honest no-network fallback
The system SHALL NOT claim that it searched or retrieved internet information unless a network tool returned a successful result for the request.

#### Scenario: Networking is enabled but no network tool is available
- **WHEN** a request allows networking but the user has no connected network-classified tool
- **THEN** the system continues with local capabilities and indicates that no online retrieval was performed

