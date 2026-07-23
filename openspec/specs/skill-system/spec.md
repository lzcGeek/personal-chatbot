## Requirements

### Requirement: Skill file format
The system SHALL support Skills defined as directories containing a `SKILL.md` file with YAML frontmatter (name, description) and Markdown content describing the skill's behavior.

#### Scenario: Valid skill loaded
- **WHEN** a skill directory contains a valid SKILL.md with frontmatter and content
- **THEN** the skill is parsed and made available for injection into the system prompt

#### Scenario: Invalid skill skipped
- **WHEN** a skill directory lacks SKILL.md or has malformed frontmatter
- **THEN** the system logs a warning and skips that skill without blocking other skills

### Requirement: Skill loading at startup
The system SHALL scan the `skills/` directory at application startup and load all valid skills into memory.

#### Scenario: Skills directory scanned
- **WHEN** the application starts
- **THEN** all valid skill directories under `skills/` are loaded and listed via the API

#### Scenario: Empty skills directory
- **WHEN** the `skills/` directory is empty or does not exist
- **THEN** the system starts normally with no skills loaded

### Requirement: Skill injection into system prompt
The system SHALL inject loaded skill content into the LLM system prompt, enabling the AI to follow skill-specific instructions.

#### Scenario: Skills included in prompt
- **WHEN** building the system prompt for a chat request
- **THEN** all loaded skill contents are appended to the system prompt under a "Skills" section

#### Scenario: Skill provides specialized behavior
- **WHEN** a skill defines specific response patterns or capabilities
- **THEN** the LLM follows those patterns when relevant to the user's request

### Requirement: Skill management API
The system SHALL provide API endpoints to list loaded skills.

#### Scenario: List loaded skills
- **WHEN** the user calls GET /api/skills
- **THEN** the system returns all loaded skills with their name, description, and load status

### Requirement: Skill hot-reload
The system SHALL support reloading skills at runtime without restarting the application.

#### Scenario: Reload skills
- **WHEN** the user calls POST /api/skills/reload
- **THEN** the system rescans the `skills/` directory and updates the loaded skills without restarting
