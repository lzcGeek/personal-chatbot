import re
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
SUPPORTED_MEDIA_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/octet-stream",
}


@dataclass(frozen=True)
class ParsedUnit:
    text: str
    page_number: int | None = None
    section: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class DocumentParser:
    @staticmethod
    def validate(filename: str, media_type: str | None) -> str:
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError("Supported document types are PDF, DOCX, TXT and Markdown")
        if media_type and media_type not in SUPPORTED_MEDIA_TYPES:
            raise ValueError("File content type is not supported")
        return ".md" if extension == ".markdown" else extension

    def parse(self, path: Path, extension: str) -> list[ParsedUnit]:
        if extension == ".pdf":
            units = self._parse_pdf(path)
        elif extension == ".docx":
            units = self._parse_docx(path)
        elif extension in {".md", ".markdown"}:
            units = self._parse_markdown(path)
        else:
            units = self._parse_text(path)
        if not units or not any(unit.text.strip() for unit in units):
            raise ValueError("No extractable text was found in the document")
        return units

    @staticmethod
    def _parse_pdf(path: Path) -> list[ParsedUnit]:
        reader = PdfReader(str(path))
        units: list[ParsedUnit] = []
        for index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                units.append(ParsedUnit(text=text, page_number=index + 1))
        return units

    @staticmethod
    def _parse_docx(path: Path) -> list[ParsedUnit]:
        document = DocxDocument(str(path))
        units: list[ParsedUnit] = []
        section: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                units.append(ParsedUnit(text="\n".join(buffer), section=section))
                buffer.clear()

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            if paragraph.style and paragraph.style.name.lower().startswith("heading"):
                flush()
                section = text
            else:
                buffer.append(text)
        flush()
        return units

    @staticmethod
    def _parse_markdown(path: Path) -> list[ParsedUnit]:
        text = DocumentParser._read_text(path)
        units: list[ParsedUnit] = []
        section: str | None = None
        buffer: list[str] = []
        for line in text.splitlines():
            heading = re.match(r"^#{1,6}\s+(.+)$", line.strip())
            if heading:
                if buffer:
                    units.append(ParsedUnit(text="\n".join(buffer).strip(), section=section))
                    buffer.clear()
                section = heading.group(1).strip()
            else:
                buffer.append(line)
        if buffer:
            units.append(ParsedUnit(text="\n".join(buffer).strip(), section=section))
        return [unit for unit in units if unit.text]

    @staticmethod
    def _parse_text(path: Path) -> list[ParsedUnit]:
        return [ParsedUnit(text=DocumentParser._read_text(path).strip())]

    @staticmethod
    def _read_text(path: Path) -> str:
        raw = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Text document encoding is not supported")
