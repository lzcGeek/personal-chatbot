import re
import uuid
from dataclasses import dataclass

from app.models.character import Character
from app.services.llm_client import LlmClient


@dataclass(frozen=True)
class SpeakerPlanDecision:
    speaker_ids: list[uuid.UUID]
    reason_code: str


class NpcOrchestrator:
    def __init__(self, llm_client: LlmClient) -> None:
        self.llm_client = llm_client

    async def select(
        self,
        strategy: str,
        content: str,
        members: list[Character],
        *,
        max_speakers: int = 1,
        target_character_id: uuid.UUID | None = None,
        previous_character_id: uuid.UUID | None = None,
    ) -> SpeakerPlanDecision:
        if not members:
            raise ValueError("Group conversation requires an enabled member")
        bounded = max(1, min(max_speakers, len(members)))
        allowed = {member.id: member for member in members}

        if strategy == "manual":
            if target_character_id not in allowed:
                raise ValueError("Manual routing requires an enabled target character")
            return SpeakerPlanDecision([target_character_id], "manual_target")

        if strategy == "mention":
            mentioned = [
                member.id
                for member in members
                if re.search(rf"(?<!\w)@{re.escape(member.name)}(?!\w)", content, re.IGNORECASE)
            ]
            if len(mentioned) == 1:
                return SpeakerPlanDecision(mentioned, "mention_unique")
            return SpeakerPlanDecision([members[0].id], "mention_ambiguous_fallback")

        if strategy == "round_robin":
            ids = [member.id for member in members]
            if previous_character_id in ids:
                index = (ids.index(previous_character_id) + 1) % len(ids)
            else:
                index = 0
            return SpeakerPlanDecision([ids[index]], "round_robin_next")

        if strategy == "auto":
            routed = await self.llm_client.route_characters(
                content,
                [{"id": str(member.id), "name": member.name} for member in members],
                bounded,
            )
            try:
                selected = [uuid.UUID(value) for value in routed]
            except (TypeError, ValueError):
                selected = []
            if (
                not selected
                or len(selected) != len(set(selected))
                or any(character_id not in allowed for character_id in selected)
            ):
                return SpeakerPlanDecision([members[0].id], "auto_invalid_fallback")
            return SpeakerPlanDecision(selected[:bounded], "auto_selected")

        raise ValueError("Unsupported routing strategy")
