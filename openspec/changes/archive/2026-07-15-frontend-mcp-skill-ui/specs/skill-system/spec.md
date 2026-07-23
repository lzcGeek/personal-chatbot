## ADDED Requirements

### Requirement: Skill creation via API
The system SHALL provide an API endpoint to create new Skills programmatically.

#### Scenario: Create a valid Skill
- **WHEN** the client sends POST /api/skills with valid JSON body containing `name`, `description`, and `content`
- **THEN** the system creates a `skills/{name}/SKILL.md` file and returns 201 with the created Skill's metadata

#### Scenario: Duplicate skill name
- **WHEN** the client sends POST /api/skills with a name that already exists as a skill directory
- **THEN** the system returns 409 Conflict with an error message

#### Scenario: Invalid skill data
- **WHEN** the client sends POST /api/skills missing the required `name` or `description` or `content` field
- **THEN** the system returns 422 with field-level validation errors
