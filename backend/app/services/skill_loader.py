import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


logger = logging.getLogger(__name__)


@dataclass
class Skill:
    name: str
    description: str
    content: str
    path: str
    status: str = "loaded"
    enabled: bool = True


class SkillLoader:
    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path
        self._skills: dict[str, Skill] = {}
        self._state_file = root_path / ".state.json"

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills.values())

    def load(self) -> list[Skill]:
        state = self._load_state()
        loaded: dict[str, Skill] = {}
        if not self.root_path.exists():
            logger.warning("Skills directory does not exist: %s", self.root_path)
            self._skills = {}
            return []

        for directory in sorted(path for path in self.root_path.iterdir() if path.is_dir()):
            skill_path = directory / "SKILL.md"
            if not skill_path.is_file():
                logger.warning("Skipping skill without SKILL.md: %s", directory)
                continue
            try:
                skill = self._parse(skill_path)
                skill.enabled = state.get(skill.name, True)
                loaded[skill.name] = skill
            except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
                logger.warning("Skipping invalid skill %s: %s", skill_path, exc)

        self._skills = loaded
        return self.skills

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        skill = self._skills.get(name)
        if skill is None:
            return False
        skill.enabled = enabled
        self._save_state()
        return True

    def prompt_section(self, triggered_skill: str | None = None) -> str:
        """Return prompt section. If triggered_skill is given, only inject that one (if enabled)."""
        if triggered_skill:
            skill = self._skills.get(triggered_skill)
            if skill and skill.enabled:
                return f"## Skill: {skill.name}\nDescription: {skill.description}\n\n{skill.content}"
            return ""

        enabled = [s for s in self._skills.values() if s.enabled]
        if not enabled:
            return ""
        sections = ["## Skills"]
        for skill in enabled:
            sections.append(f"### {skill.name}\nDescription: {skill.description}\n\n{skill.content}")
        return "\n\n".join(sections)

    def as_dicts(self) -> list[dict]:
        return [asdict(skill) for skill in self._skills.values()]

    def _load_state(self) -> dict[str, bool]:
        try:
            if self._state_file.is_file():
                return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def _save_state(self) -> None:
        try:
            self._state_file.write_text(
                json.dumps({name: skill.enabled for name, skill in self._skills.items()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("Failed to save skill state")

    @staticmethod
    def _parse(path: Path) -> Skill:
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---\n"):
            raise ValueError("missing YAML frontmatter")
        try:
            _, frontmatter, content = raw.split("---", 2)
        except ValueError as exc:
            raise ValueError("unterminated YAML frontmatter") from exc

        metadata = yaml.safe_load(frontmatter)
        if not isinstance(metadata, dict):
            raise ValueError("frontmatter must be a mapping")
        name = metadata.get("name")
        description = metadata.get("description")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("frontmatter name is required")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("frontmatter description is required")
        if not content.strip():
            raise ValueError("skill instructions are empty")

        return Skill(
            name=name.strip(),
            description=description.strip(),
            content=content.strip(),
            path=str(path),
        )
