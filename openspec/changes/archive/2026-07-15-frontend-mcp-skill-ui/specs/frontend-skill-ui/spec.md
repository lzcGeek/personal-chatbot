## ADDED Requirements

### Requirement: Skill list display
The frontend SHALL display all loaded Skills with their name, description, and load status.

#### Scenario: List shows loaded skills
- **WHEN** the user opens the Skill management tab
- **THEN** all loaded Skills are displayed with name, description, and a "loaded" status indicator

#### Scenario: Empty skill list
- **WHEN** no Skills are loaded
- **THEN** the tab shows a placeholder message suggesting the user create or reload Skills

### Requirement: Create new Skill via editor
The frontend SHALL provide a text editor to create new Skills, with a template pre-populated with YAML frontmatter structure.

#### Scenario: Open new skill editor
- **WHEN** the user clicks "新建 Skill"
- **THEN** a textarea appears with YAML frontmatter skeleton (name and description fields) and a blank Markdown body

#### Scenario: Save new skill
- **WHEN** the user writes valid frontmatter + content and saves
- **THEN** the Skill is created on the server, and the editor closes with a success confirmation

#### Scenario: Duplicate skill name
- **WHEN** the user saves a Skill whose name already exists
- **THEN** an error message is displayed and the Skill is not overwritten

#### Scenario: Missing required fields
- **WHEN** the user saves without providing a name
- **THEN** the system SHALL display a validation error and not send the request

### Requirement: Hot-reload Skills
The frontend SHALL provide a button to trigger Skill hot-reload without restarting the application.

#### Scenario: Reload triggers re-scan
- **WHEN** the user clicks the reload button
- **THEN** the server re-scans the skills directory and the frontend updates the list with any changes

#### Scenario: Reload feedback
- **WHEN** reload completes
- **THEN** a brief success message shows the count of loaded Skills
