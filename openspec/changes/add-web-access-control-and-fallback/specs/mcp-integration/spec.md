## MODIFIED Requirements

### Requirement: MCP Tool discovery
The system SHALL automatically discover tools from connected MCP Servers, associate each tool route with its server's network classification, and expose only tools permitted by the current chat request.

#### Scenario: Tools discovered on connection
- **WHEN** an MCP Server successfully connects
- **THEN** the system retrieves the server's tool list, stores the tools with the server route and network classification, and marks the connection as active

#### Scenario: Tools included in LLM context
- **WHEN** building context for a chat request
- **THEN** the system includes descriptions of available tools whose classification is allowed by that request so the LLM can decide when to call them

#### Scenario: Network tools excluded from LLM context
- **WHEN** building context for a chat request that does not allow network access
- **THEN** the system excludes every tool belonging to a server classified as requiring network access

### Requirement: MCP Tool invocation in chat
The system SHALL allow the LLM to invoke an MCP tool only when it belongs to the authenticated user, is connected and enabled, and is permitted by the current request's network policy, sending the structured tool result back to the LLM for response generation.

#### Scenario: LLM calls an allowed MCP tool
- **WHEN** the LLM response indicates a tool call to an available tool permitted by the current request
- **THEN** the system executes it via the MCP Server, appends the result to the conversation context, and requests a follow-up response from the LLM

#### Scenario: MCP tool call fails
- **WHEN** an MCP tool call fails because of timeout, disconnection, validation, or server error
- **THEN** the system returns a structured error result to the LLM so it can report the failure or continue without that tool

#### Scenario: LLM calls a disallowed network tool
- **WHEN** execution is requested for a network-classified tool but the current request does not allow network access
- **THEN** the system refuses execution before enqueueing the call and returns `network_access_denied`

## ADDED Requirements

### Requirement: MCP server network classification
The system SHALL store whether each MCP server requires network permission and SHALL allow its owner to view and update that classification.

#### Scenario: New HTTP or SSE server is created without an explicit classification
- **WHEN** a user creates an HTTP or SSE MCP server and omits `requires_network`
- **THEN** the system classifies the server as requiring network permission

#### Scenario: New stdio server is created without an explicit classification
- **WHEN** a user creates a stdio MCP server and omits `requires_network`
- **THEN** the system classifies the server as not requiring network permission and presents the classification for user review

