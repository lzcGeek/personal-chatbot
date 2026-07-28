import re
from dataclasses import dataclass

from app.services.document_parser import ParsedUnit


@dataclass(frozen=True)
class PreparedChunk:
    ordinal: int
    content: str
    context_text: str
    page_number: int | None
    section: str | None
    metadata: dict[str, object]


class DocumentChunker:
    def __init__(self, chunk_characters: int, overlap_characters: int, context_window: int) -> None:
        self.chunk_characters = chunk_characters
        self.overlap_characters = min(overlap_characters, chunk_characters // 2)
        self.context_window = context_window

    def chunk(self, units: list[ParsedUnit]) -> list[PreparedChunk]:
        focused: list[tuple[str, ParsedUnit]] = []
        for unit in units:
            for text in self._split(unit.text):
                if text.strip():
                    focused.append((text.strip(), unit))
        chunks: list[PreparedChunk] = []
        for index, (content, unit) in enumerate(focused):
            start = max(0, index - self.context_window)
            end = min(len(focused), index + self.context_window + 1)
            context = "\n\n".join(item[0] for item in focused[start:end])
            chunks.append(
                PreparedChunk(
                    ordinal=index,
                    content=content,
                    context_text=context,
                    page_number=unit.page_number,
                    section=unit.section,
                    metadata=unit.metadata,
                )
            )
        return chunks

    def _split(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        result: list[str] = []
        for paragraph in paragraphs or [text]:
            cursor = 0
            while cursor < len(paragraph):
                end = min(len(paragraph), cursor + self.chunk_characters)
                if end < len(paragraph):
                    boundary = max(
                        paragraph.rfind("。", cursor, end),
                        paragraph.rfind("！", cursor, end),
                        paragraph.rfind("？", cursor, end),
                        paragraph.rfind(". ", cursor, end),
                        paragraph.rfind("\n", cursor, end),
                    )
                    if boundary > cursor + self.chunk_characters // 2:
                        end = boundary + 1
                result.append(paragraph[cursor:end].strip())
                if end >= len(paragraph):
                    break
                cursor = max(cursor + 1, end - self.overlap_characters)
        return [item for item in result if item]
