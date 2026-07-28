## 1. Specification & Infrastructure

- [x] 1.1 Create proposal, design and task artifacts
- [x] 1.2 Add PostgreSQL/Qdrant Docker Compose and environment template
- [x] 1.3 Add Alembic initial migration and database startup documentation

## 2. Authentication

- [x] 2.1 Add User and UserSession models
- [x] 2.2 Add Argon2id password and opaque Cookie Session service
- [x] 2.3 Add register/login/logout/me API and CSRF validation
- [x] 2.4 Add frontend authentication store and login/register UI

## 3. User Isolation

- [x] 3.1 Scope conversations and messages to current user
- [x] 3.2 Scope memory list/search/delete to current user
- [x] 3.3 Scope MCP persistence and tool routes to current user
- [x] 3.4 Require authentication for Skills management

## 4. Vector Memory

- [x] 4.1 Add explicit OpenAI-compatible embedding service
- [x] 4.2 Add Qdrant collection manager and filtered retrieval
- [x] 4.3 Add PostgreSQL vector outbox and worker
- [x] 4.4 Handle memory and conversation vector deletion through outbox

## 5. Verification

- [x] 5.1 Run Python compile/import checks
- [x] 5.2 Run frontend typecheck/build
- [x] 5.3 Verify database containers, migrations and health endpoints
- [ ] 5.4 Verify user A cannot access user B conversations, memories or MCP servers
