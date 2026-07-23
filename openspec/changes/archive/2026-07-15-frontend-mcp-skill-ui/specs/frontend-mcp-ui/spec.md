## ADDED Requirements

### Requirement: MCP Server list display
The frontend SHALL display all registered MCP Servers in a list showing each server's name, transport type (stdio / SSE / HTTP), connection status (connected / disconnected), and tool count.

#### Scenario: List shows connected server
- **WHEN** the user opens the MCP management tab and a server is connected
- **THEN** the server appears with a green status indicator, transport icon, and tool count

#### Scenario: List shows disconnected server
- **WHEN** a server's connection fails
- **THEN** the server remains in the list with a red status indicator and a reconnect hint

### Requirement: Add MCP Server form with transport toggle
The frontend SHALL provide a form to add new MCP Servers, with form fields that change based on the selected transport type.

#### Scenario: stdio form fields
- **WHEN** the user selects "stdio" transport
- **THEN** the form shows command (required), args (optional), and env (optional) text fields

#### Scenario: SSE form fields
- **WHEN** the user selects "SSE" transport
- **THEN** the form shows a URL field (required) and hides command/args fields

#### Scenario: HTTP form fields
- **WHEN** the user selects "HTTP" transport
- **THEN** the form shows a URL field (required) and hides command/args fields

#### Scenario: Successful server addition
- **WHEN** the user fills valid fields and submits
- **THEN** the server appears in the list and connection is attempted

#### Scenario: Connection failure feedback
- **WHEN** adding a server fails (connection timeout or validation error)
- **THEN** the form displays the error message and the server is not saved

### Requirement: Delete MCP Server
The frontend SHALL allow the user to remove a configured MCP Server.

#### Scenario: Delete with confirmation
- **WHEN** the user clicks delete on a server
- **THEN** a confirmation prompt appears before the server is disconnected and removed from the list

#### Scenario: Delete cancelled
- **WHEN** the user dismisses the confirmation prompt
- **THEN** the server remains unchanged
