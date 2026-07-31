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
            splitter = (
                self._split_table
                if unit.metadata.get("content_type") == "table"
                else self._split
            )
            for text in splitter(unit.text):
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
        buffer = ""

        def flush_buffer() -> None:
            nonlocal buffer
            if buffer:
                result.append(buffer)
                buffer = ""

        for paragraph in paragraphs or [text]:
            if len(paragraph) <= self.chunk_characters:
                candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
                if len(candidate) <= self.chunk_characters:
                    buffer = candidate
                    continue
                flush_buffer()
                buffer = paragraph
                continue

            flush_buffer()
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
        flush_buffer()
        return [item for item in result if item]

    def _split_table(self, text: str) -> list[str]:
        """Split Markdown tables by rows while repeating the column header."""
        if len(text) <= self.chunk_characters:
            return [text]
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        header_index = next(
            (
                index
                for index in range(len(lines) - 1)
                if lines[index].startswith("|")
                and re.fullmatch(r"\|(?:\s*:?-{3,}:?\s*\|)+", lines[index + 1])
            ),
            None,
        )
        if header_index is None:
            return self._split(text)

        prefix = lines[:header_index]
        repeated = [*prefix, lines[header_index], lines[header_index + 1]]
        repeated_text = "\n".join(repeated)
        if len(repeated_text) >= self.chunk_characters:
            return self._split(text)

        chunks: list[str] = []
        current = repeated.copy()
        for row in lines[header_index + 2 :]:
            candidate = "\n".join([*current, row])
            if len(candidate) <= self.chunk_characters:
                current.append(row)
                continue
            if len(current) > len(repeated):
                chunks.append("\n".join(current))
                current = repeated.copy()
            if len("\n".join([*current, row])) <= self.chunk_characters:
                current.append(row)
            else:
                # An unusually large cell cannot preserve both the full header
                # and the configured limit, so fall back to bounded text chunks.
                chunks.extend(self._split(row))
        if len(current) > len(repeated):
            chunks.append("\n".join(current))
        return chunks or self._split(text)
