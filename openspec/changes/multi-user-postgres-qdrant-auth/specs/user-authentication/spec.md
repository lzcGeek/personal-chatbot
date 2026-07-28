## ADDED Requirements

### Requirement: Password authentication
The system SHALL store only Argon2id password hashes and SHALL return a generic error for invalid credentials.

#### Scenario: Successful login
- **WHEN** an active user submits a valid username and password
- **THEN** the system creates a server-side session and returns a protected session Cookie

#### Scenario: Invalid login
- **WHEN** a username or password is invalid
- **THEN** the system returns the same unauthorized response without revealing which field was wrong

### Requirement: Cookie session
The system SHALL authenticate requests using an opaque high-entropy token in an HttpOnly Cookie while storing only the token hash in PostgreSQL.

#### Scenario: Logout
- **WHEN** an authenticated user logs out
- **THEN** the server revokes the session and expires the browser Cookie

### Requirement: CSRF protection
The system SHALL validate CSRF and request Origin for authenticated state-changing requests.

#### Scenario: Missing CSRF token
- **WHEN** an authenticated POST, PATCH, PUT or DELETE request omits a valid CSRF token
- **THEN** the system rejects the request
